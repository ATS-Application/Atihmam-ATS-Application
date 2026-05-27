# app/services/scoring_service.py
# =============================================================================
# CE FICHIER EST LE CŒUR DU SYSTÈME DE NOTATION DES CANDIDATS.
#
# Son rôle : comparer un CV avec une offre d'emploi et produire un score
# de 0 à 100 qui indique à quel point le candidat correspond au poste.
#
# Pour faire ça, il analyse plusieurs "dimensions" :
#   - Les mots-clés en commun entre le CV et l'offre
#   - La similarité sémantique (le "sens" des textes, pas juste les mots)
#   - Les années d'expérience du candidat vs ce qui est demandé
#   - Les certifications détectées
#   - Le niveau d'études
#   - Les termes de leadership (chef, manager, etc.)
#   - La complexité des projets mentionnés
#
# Chaque dimension a un "poids" (importance relative dans le score final).
# Ces poids peuvent changer automatiquement selon les retours utilisateurs
# (système d'apprentissage adaptatif).
#
# Le système détecte aussi automatiquement le DOMAINE du poste
# (Informatique, Finance, Santé, BTP, etc.) pour adapter les critères
# de notation : un comptable n'a pas besoin de connaître Docker !
# =============================================================================

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# -----------------------------------------------------------------------------
# DOSSIER DE CACHE POUR LES MODÈLES D'IA
# -----------------------------------------------------------------------------
# SentenceTransformer (le modèle qui comprend le sens des textes) est un gros
# fichier qui se télécharge depuis HuggingFace. On le met en cache dans un
# dossier local ".hf-cache" pour ne pas le retélécharger à chaque démarrage.
#
# IMPORTANT : les variables d'environnement HF_HOME et TRANSFORMERS_CACHE
# DOIVENT être définies AVANT d'importer la librairie transformers,
# sinon elle ignore ces chemins. C'est pourquoi ce bloc est tout en haut.
# -----------------------------------------------------------------------------
_CACHE_DIR = Path("./.hf-cache")
_CACHE_DIR.mkdir(exist_ok=True)
os.environ["HF_HOME"] = str(_CACHE_DIR.resolve())
os.environ["TRANSFORMERS_CACHE"] = str(_CACHE_DIR.resolve())


# -----------------------------------------------------------------------------
# CHARGEMENT DU MODÈLE D'IA (SENTENCE TRANSFORMER)
# -----------------------------------------------------------------------------
# "all-MiniLM-L6-v2" est un modèle léger mais performant.
# Il transforme un texte en un vecteur de nombres (un "embedding").
# Deux textes avec un sens similaire auront des vecteurs proches.
# C'est ce qui permet de comparer sémantiquement un CV et une offre d'emploi.
#
# @lru_cache(maxsize=1) : le modèle est lourd à charger (~80MB).
# Cette décoration Python mémorise le résultat du premier appel.
# Tous les appels suivants retournent le modèle déjà chargé en mémoire
# sans le recharger. C'est un singleton de facto.
# -----------------------------------------------------------------------------
_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    print(f"[scoring] Loading SentenceTransformer ({_MODEL_NAME})…")
    return SentenceTransformer(_MODEL_NAME)


# =============================================================================
# TAXONOMIE DES DOMAINES MÉTIER
# =============================================================================
# Un "domaine" représente le secteur professionnel d'un poste.
# La détection du domaine est cruciale car elle change complètement
# les critères de notation :
#
#   → Domaines TECH (TECH_DOMAINS) : on cherche des mots-clés techniques
#     (Python, Docker, Kubernetes...) et des certifications IT (AWS, Scrum...).
#
#   → Domaines NON-TECH (tous les autres) : on utilise des mots-clés
#     spécifiques au métier (ex: "OHADA", "IFRS" pour la comptabilité)
#     et on ignore les certifications IT qui ne sont pas pertinentes.
#
# Domain hérite de str et Enum pour que chaque valeur soit à la fois
# une constante et une chaîne de caractères lisible (utile pour les logs
# et la sérialisation JSON).
# =============================================================================

class Domain(str, Enum):
    # --- Domaines TECHNIQUES : utilisent le pipeline de scoring tech original ---
    TECH            = "Informatique & Développement logiciel"
    NETWORKS        = "Réseaux, Télécoms & Cybersécurité"
    ENGINEERING     = "Ingénierie & Techniques"
    SCIENCE         = "Sciences & Recherche"
    ENERGY          = "Énergie, Mines & Pétrole"
    INDUSTRY        = "Production & Industrie"
    QHSE            = "Qualité, Hygiène, Sécurité, Environnement (QHSE)"

    # --- Domaines NON-TECHNIQUES : utilisent un profil de scoring personnalisé ---
    SUPPLY_CHAIN    = "Achats & Supply Chain"
    ADMIN           = "Administration & Secrétariat"
    AGRI            = "Agriculture & Agroalimentaire"
    ART             = "Art, Culture & Design"
    BANKING         = "Banque & Assurance"
    SALES           = "Commercial & Vente"
    ACCOUNTING      = "Comptabilité & Finance"
    BTP             = "Construction & BTP"
    LEGAL           = "Droit & Juridique"
    EDUCATION       = "Éducation & Formation"
    HOSPITALITY     = "Hôtellerie & Restauration"
    REAL_ESTATE     = "Immobilier"
    JOURNALISM      = "Journalisme & Médias"
    MARKETING       = "Marketing & Communication"
    HR              = "Ressources Humaines (RH)"
    HEALTH          = "Santé & Médical"
    GENERAL_SERVICES= "Services Généraux"
    INTERN          = "Stage / Jeune diplômé"
    TOURISM         = "Tourisme & Loisirs"
    TRANSPORT       = "Transport & Logistique"
    SOCIAL          = "Travail Social & ONG"


# frozenset (ensemble immuable) des domaines qui gardent le pipeline technique.
# frozenset est plus rapide qu'un set pour les tests d'appartenance ("in").
TECH_DOMAINS: frozenset[Domain] = frozenset({
    Domain.TECH,
    Domain.NETWORKS,
    Domain.ENGINEERING,
    Domain.SCIENCE,
    Domain.ENERGY,
    Domain.INDUSTRY,
    Domain.QHSE,
})


# -----------------------------------------------------------------------------
# PROFIL DE DOMAINE (pour les domaines non-techniques)
# -----------------------------------------------------------------------------
# Un DomainProfile définit comment scorer un domaine métier spécifique.
# Chaque domaine a ses propres :
#
#   keywords        : mots-clés pertinents pour ce métier
#                     (remplace TECH_KEYWORDS pour les non-tech)
#
#   indicators      : termes qui indiquent une expertise avancée,
#                     avec un nombre de points attribués à chacun
#                     (ex: "ISO 9001" vaut 20 points pour le QHSE)
#
#   weight_overrides: permet de redéfinir l'importance de chaque dimension
#                     pour ce domaine. Par exemple, pour un poste de Stage,
#                     l'éducation compte plus que l'expérience.
#                     Les clés non listées conservent les DEFAULT_WEIGHTS.
#                     Le résultat final est toujours normalisé (somme = 1).
#
#   leadership_terms: vocabulaire de leadership propre au domaine
#                     (ex: "DRH" pour les RH, "chef de chantier" pour le BTP)
#                     Ces termes s'ajoutent à la liste globale LEADERSHIP_TERMS.
#
# @dataclass génère automatiquement __init__, __repr__, etc.
# field(default_factory=...) crée une nouvelle instance vide à chaque fois
# (évite le piège classique des arguments mutables partagés entre instances).
# -----------------------------------------------------------------------------
@dataclass
class DomainProfile:
    keywords         : tuple[str, ...]         = field(default_factory=tuple)
    indicators       : dict[str, int]          = field(default_factory=dict)
    weight_overrides : dict[str, float]        = field(default_factory=dict)
    leadership_terms : tuple[str, ...]         = field(default_factory=tuple)


# -----------------------------------------------------------------------------
# SIGNAUX DE DÉTECTION DE DOMAINE
# -----------------------------------------------------------------------------
# Ce dictionnaire sert UNIQUEMENT à identifier le domaine d'un poste.
# Il ne sert PAS au scoring.
#
# Pour chaque domaine, on liste des mots-clés "forts" (en minuscules)
# qui indiquent clairement qu'on est dans ce secteur.
#
# La fonction classify_domain() compte combien de ces signaux apparaissent
# dans le texte combiné (CV + titre du poste + exigences), et choisit
# le domaine avec le plus de correspondances.
#
# frozenset par domaine : les recherches "x in frozenset" sont O(1),
# ce qui est important car on parcourt tous les domaines pour chaque scoring.
# -----------------------------------------------------------------------------
_DOMAIN_DETECTION: dict[Domain, frozenset[str]] = {
    Domain.TECH:          frozenset({"python", "java", "react", "docker", "kubernetes",
                                     "api", "backend", "frontend", "devops", "software",
                                     "développement logiciel", "informatique", "programmation"}),
    Domain.NETWORKS:      frozenset({"réseau", "network", "cybersécurité", "cisco", "firewall",
                                     "switch", "vpn", "télécoms", "infrastructure réseau"}),
    Domain.ENGINEERING:   frozenset({"mécanique", "électrique", "conception", "autocad",
                                     "solidworks", "bureau d'études", "ingénierie"}),
    Domain.SCIENCE:       frozenset({"laboratoire", "recherche", "publication", "thèse",
                                     "protocole", "expérimentation", "chimie", "biologie"}),
    Domain.ENERGY:        frozenset({"pétrole", "mines", "forage", "géologie", "raffinage",
                                     "énergie renouvelable", "solaire", "hydraulique"}),
    Domain.INDUSTRY:      frozenset({"production", "usine", "chaîne de montage", "lean",
                                     "maintenance industrielle", "5s", "kaizen"}),
    Domain.QHSE:          frozenset({"hse", "qualité", "iso 9001", "iso 14001", "sécurité au travail",
                                     "audit qualité", "non-conformité", "certification qhse"}),
    Domain.SUPPLY_CHAIN:  frozenset({"achat", "supply chain", "approvisionnement", "logistique",
                                     "fournisseur", "négociation achat", "erp", "stock"}),
    Domain.ADMIN:         frozenset({"secrétariat", "assistante", "agenda", "courrier",
                                     "accueil", "classement", "bureautique", "archivage"}),
    Domain.AGRI:          frozenset({"agriculture", "élevage", "agronomie", "semences",
                                     "cultures", "agroalimentaire", "terrain agricole"}),
    Domain.ART:           frozenset({"design", "graphisme", "photographie", "illustration",
                                     "créatif", "adobe", "figma", "ux", "ui", "artiste"}),
    Domain.BANKING:       frozenset({"banque", "assurance", "crédit", "risque", "bâle",
                                     "conformité", "actuariat", "portefeuille clients"}),
    Domain.SALES:         frozenset({"vente", "commercial", "prospection", "crm", "ca",
                                     "chiffre d'affaires", "b2b", "b2c", "négociation commerciale"}),
    Domain.ACCOUNTING:    frozenset({"comptabilité", "fiscalité", "bilan", "audit financier",
                                     "ifrs", "ohada", "contrôle de gestion", "trésorerie"}),
    Domain.BTP:           frozenset({"construction", "btp", "chantier", "génie civil",
                                     "maçonnerie", "conducteur de travaux", "bâtiment"}),
    Domain.LEGAL:         frozenset({"droit", "juridique", "contrat", "avocat", "notaire",
                                     "procédure", "contentieux", "réglementation"}),
    Domain.EDUCATION:     frozenset({"enseignement", "formateur", "pédagogie", "curriculum",
                                     "professeur", "élèves", "formation professionnelle"}),
    Domain.HOSPITALITY:   frozenset({"hôtellerie", "restauration", "cuisine", "chef",
                                     "service en salle", "accueil client", "f&b"}),
    Domain.REAL_ESTATE:   frozenset({"immobilier", "transaction", "bail", "copropriété",
                                     "expertise immobilière", "promotion immobilière"}),
    Domain.JOURNALISM:    frozenset({"journalisme", "rédaction", "médias", "presse",
                                     "reportage", "édition", "publication", "contenu éditorial"}),
    Domain.MARKETING:     frozenset({"marketing", "communication", "stratégie digitale",
                                     "seo", "sem", "brand", "campagne", "publicité"}),
    Domain.HR:            frozenset({"ressources humaines", "recrutement", "paie", "gpec",
                                     "formation", "relations sociales", "rh", "talent"}),
    Domain.HEALTH:        frozenset({"médecin", "infirmier", "pharmacie", "santé", "clinique",
                                     "patient", "soins", "hôpital", "médical"}),
    Domain.GENERAL_SERVICES: frozenset({"maintenance", "facility", "nettoyage", "gardiennage",
                                         "services généraux", "prestataires"}),
    Domain.INTERN:        frozenset({"stage", "jeune diplômé", "alternance", "apprentissage"}),
    Domain.TOURISM:       frozenset({"tourisme", "voyage", "hôtel", "agence de voyage",
                                     "guide touristique", "loisirs"}),
    Domain.TRANSPORT:     frozenset({"transport", "logistique", "chauffeur", "fret",
                                     "douane", "transit", "fleet management"}),
    Domain.SOCIAL:        frozenset({"travail social", "ong", "humanitaire", "développement communautaire",
                                     "action sociale", "volontariat", "ngo"}),
}


# -----------------------------------------------------------------------------
# PROFILS DE SCORING PAR DOMAINE NON-TECHNIQUE
# -----------------------------------------------------------------------------
# Chaque entrée de ce dictionnaire définit les règles de scoring spécifiques
# à un domaine métier.
#
# Exemple de lecture pour Domain.ACCOUNTING :
#   - keywords : "comptabilité", "IFRS", "OHADA", "Sage", etc.
#     → Si ces mots apparaissent à la fois dans le CV ET l'offre, le score
#       de mots-clés monte.
#   - indicators : "ifrs" = 20 pts, "ohada" = 20 pts, "audit externe" = 20 pts...
#     → Présents dans le CV, ces termes indiquent une expertise poussée.
#   - weight_overrides : keyword=25%, sémantique=30%, expérience=20%,
#       éducation=15%, complexité=5%, leadership=5%
#     → Pour la comptabilité, l'éducation (diplôme) compte plus que la moyenne.
#
# Note : les domaines de la famille TECH (NETWORKS, ENGINEERING, etc.) ont
# aussi des profils ici pour étendre les mots-clés et indicateurs tech,
# mais ils restent dans le pipeline "tech" (TECH_DOMAINS).
# -----------------------------------------------------------------------------
_DOMAIN_PROFILES: dict[Domain, DomainProfile] = {
    Domain.SUPPLY_CHAIN: DomainProfile(
        keywords=("achat", "approvisionnement", "supply chain", "erp", "sap",
                  "négociation", "fournisseur", "inventaire", "logistique",
                  "appel d'offres", "sourcing", "stock", "s&op"),
        indicators={"sap": 20, "erp": 15, "s&op": 20, "négociation": 15,
                    "sourcing international": 20, "réduction coûts": 15},
        weight_overrides={"keyword": 0.25, "semantic": 0.35, "experience": 0.20,
                          "leadership": 0.10, "complexity": 0.05, "education": 0.05},
        leadership_terms=("chef des achats", "responsable supply chain", "directeur achats"),
    ),
    Domain.ADMIN: DomainProfile(
        keywords=("secrétariat", "bureautique", "word", "excel", "agenda",
                  "courrier", "classement", "archivage", "accueil", "office"),
        indicators={"bilingue": 20, "office 365": 15, "gestion agenda": 15},
        # Pour l'admin, la sémantique (sens général du texte) compte beaucoup
        # car les tâches sont variées et difficiles à résumer en mots-clés précis.
        weight_overrides={"keyword": 0.20, "semantic": 0.40, "experience": 0.20,
                          "education": 0.10, "leadership": 0.05, "complexity": 0.05},
    ),
    Domain.AGRI: DomainProfile(
        keywords=("agronomie", "agriculture", "élevage", "cultures", "semences",
                  "irrigation", "fertilisation", "agroalimentaire", "phytosanitaire"),
        indicators={"agriculture biologique": 20, "certification bio": 20,
                    "gestion d'exploitation": 15, "irrigation": 10},
        weight_overrides={"keyword": 0.20, "semantic": 0.35, "experience": 0.25,
                          "education": 0.10, "complexity": 0.05, "leadership": 0.05},
    ),
    Domain.ART: DomainProfile(
        keywords=("design", "graphisme", "illustrator", "photoshop", "figma",
                  "ux", "ui", "créatif", "branding", "motion design",
                  "photographie", "vidéo", "3d", "after effects"),
        indicators={"direction artistique": 20, "identité visuelle": 15,
                    "motion design": 15, "ux research": 20},
        weight_overrides={"keyword": 0.25, "semantic": 0.35, "experience": 0.15,
                          "education": 0.10, "complexity": 0.10, "leadership": 0.05},
    ),
    Domain.BANKING: DomainProfile(
        keywords=("banque", "assurance", "crédit", "risque", "portefeuille",
                  "conformité", "bâle iii", "solvabilité", "actuariat",
                  "kyc", "aml", "produits financiers", "taux"),
        # Bâle III, KYC/AML et IFRS 9 sont des normes réglementaires très
        # spécifiques → leur présence dans un CV signale une expertise réelle.
        indicators={"bâle iii": 20, "kyc/aml": 20, "actuariat": 20,
                    "gestion risque": 15, "ifrs 9": 20},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.20,
                          "education": 0.10, "complexity": 0.10, "leadership": 0.05},
    ),
    Domain.SALES: DomainProfile(
        keywords=("vente", "commercial", "prospection", "crm", "b2b", "b2c",
                  "négociation", "chiffre d'affaires", "pipeline", "closing",
                  "account manager", "fidélisation", "développement commercial"),
        indicators={"développement commercial": 15, "grand compte": 20,
                    "b2b": 10, "crm": 10, "objectifs dépassés": 20},
        # Pour la vente, l'expérience terrain (0.25) prime sur l'éducation (0.05).
        weight_overrides={"keyword": 0.20, "semantic": 0.30, "experience": 0.25,
                          "complexity": 0.10, "leadership": 0.10, "education": 0.05},
        leadership_terms=("directeur commercial", "chef des ventes", "key account manager"),
    ),
    Domain.ACCOUNTING: DomainProfile(
        keywords=("comptabilité", "fiscalité", "bilan", "ohada", "ifrs",
                  "contrôle de gestion", "audit", "trésorerie", "sage",
                  "déclarations fiscales", "rapprochement bancaire", "budget"),
        indicators={"ifrs": 20, "ohada": 20, "audit externe": 20,
                    "contrôle de gestion": 15, "sage": 10},
        # En comptabilité, le diplôme (education=0.15) est plus valorisé
        # que dans beaucoup d'autres domaines non-tech.
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.20,
                          "education": 0.15, "complexity": 0.05, "leadership": 0.05},
    ),
    Domain.BTP: DomainProfile(
        keywords=("construction", "btp", "génie civil", "conducteur de travaux",
                  "chantier", "maçonnerie", "béton armé", "autocad",
                  "planification", "lot technique", "métré", "vrd"),
        indicators={"conducteur de travaux senior": 20, "autocad": 15,
                    "gestion multi-chantiers": 20, "vrd": 15, "béton armé": 10},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.25,
                          "education": 0.10, "complexity": 0.05, "leadership": 0.05},
        leadership_terms=("directeur de travaux", "chef de chantier", "ingénieur génie civil"),
    ),
    Domain.LEGAL: DomainProfile(
        keywords=("droit", "juridique", "contrat", "contentieux", "procédure",
                  "réglementation", "conformité", "ohada", "droit du travail",
                  "droit des sociétés", "code civil", "tribunal"),
        indicators={"droit ohada": 20, "contentieux complexe": 20,
                    "contrats internationaux": 20, "droit des affaires": 15},
        # En droit, éducation (0.20) et mots-clés (0.25) dominent.
        # La complexité (0.03) et le leadership (0.02) ont peu de poids :
        # le titre de "chef" importe moins que la spécialité juridique.
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.20,
                          "education": 0.20, "complexity": 0.03, "leadership": 0.02},
    ),
    Domain.EDUCATION: DomainProfile(
        keywords=("enseignement", "formation", "pédagogie", "curriculum",
                  "e-learning", "évaluation", "professeur", "ingénierie pédagogique"),
        indicators={"ingénierie pédagogique": 20, "e-learning": 15,
                    "formation certifiante": 20},
        weight_overrides={"keyword": 0.20, "semantic": 0.35, "experience": 0.20,
                          "education": 0.15, "complexity": 0.05, "leadership": 0.05},
    ),
    Domain.HOSPITALITY: DomainProfile(
        keywords=("hôtellerie", "restauration", "cuisine", "service en salle",
                  "f&b", "sommellerie", "haccp", "réception", "housekeeping"),
        indicators={"étoile michelin": 20, "haccp": 15, "revenue management": 20,
                    "classification hôtelière": 15},
        # L'hôtellerie-restauration valorise fortement l'expérience terrain (0.30).
        weight_overrides={"keyword": 0.20, "semantic": 0.30, "experience": 0.30,
                          "education": 0.08, "complexity": 0.07, "leadership": 0.05},
    ),
    Domain.REAL_ESTATE: DomainProfile(
        keywords=("immobilier", "transaction", "bail", "promotion immobilière",
                  "expertise", "copropriété", "aménagement", "négociation immobilière"),
        indicators={"promotion immobilière": 20, "expertise immobilière": 20,
                    "vente de programmes": 15},
        weight_overrides={"keyword": 0.20, "semantic": 0.35, "experience": 0.25,
                          "education": 0.08, "complexity": 0.07, "leadership": 0.05},
    ),
    Domain.JOURNALISM: DomainProfile(
        keywords=("journalisme", "rédaction", "presse", "reportage", "médias",
                  "enquête", "édition", "contenu éditorial", "interview",
                  "photojournalisme", "digital media"),
        indicators={"grand reportage": 20, "rédacteur en chef": 20,
                    "digital media": 15},
        # Le journalisme repose beaucoup sur la sémantique (0.40) car
        # la qualité rédactionnelle est difficile à capturer avec des mots-clés seuls.
        weight_overrides={"keyword": 0.20, "semantic": 0.40, "experience": 0.20,
                          "education": 0.08, "complexity": 0.07, "leadership": 0.05},
    ),
    Domain.MARKETING: DomainProfile(
        keywords=("marketing", "communication", "seo", "sem", "google ads",
                  "social media", "brand", "campagne", "inbound", "cms",
                  "stratégie digitale", "content marketing", "kpi"),
        indicators={"stratégie omnicanale": 20, "google ads": 15,
                    "brand management": 20, "inbound marketing": 15,
                    "marketing automation": 20},
        weight_overrides={"keyword": 0.25, "semantic": 0.35, "experience": 0.18,
                          "education": 0.07, "complexity": 0.10, "leadership": 0.05},
    ),
    Domain.HR: DomainProfile(
        keywords=("recrutement", "paie", "gpec", "sirh", "droit du travail",
                  "formation", "relations sociales", "talent management",
                  "onboarding", "évaluation des performances", "rémunération"),
        indicators={"gpec": 20, "sirh": 15, "négociation syndicale": 20,
                    "talent management": 15, "rémunération variable": 10},
        weight_overrides={"keyword": 0.22, "semantic": 0.33, "experience": 0.20,
                          "education": 0.10, "complexity": 0.10, "leadership": 0.05},
        leadership_terms=("drh", "directeur des ressources humaines", "hr business partner"),
    ),
    Domain.HEALTH: DomainProfile(
        keywords=("médecine", "soins infirmiers", "pharmacie", "chirurgie",
                  "diagnostic", "patient", "urgences", "bloc opératoire",
                  "radiologie", "biologie médicale", "clinique", "protocole médical"),
        indicators={"spécialité médicale": 25, "chef de service": 20,
                    "recherche clinique": 20, "urgences": 15},
        # La santé valorise fortement l'éducation (0.18) car les diplômes médicaux
        # sont obligatoires et réglementés. Le leadership (0.03) compte peu
        # car le titre seul ne reflète pas la compétence clinique.
        weight_overrides={"keyword": 0.20, "semantic": 0.30, "experience": 0.25,
                          "education": 0.18, "complexity": 0.04, "leadership": 0.03},
    ),
    Domain.GENERAL_SERVICES: DomainProfile(
        keywords=("facility management", "maintenance", "nettoyage", "gardiennage",
                  "prestataires", "services généraux", "parc automobile", "hse"),
        indicators={"facility management": 20, "gestion prestataires": 15},
        weight_overrides={"keyword": 0.20, "semantic": 0.35, "experience": 0.25,
                          "education": 0.08, "complexity": 0.07, "leadership": 0.05},
    ),
    Domain.INTERN: DomainProfile(
        keywords=("stage", "alternance", "apprentissage", "projet académique",
                  "mémoire", "rapport de stage"),
        indicators={"projet transversal": 10, "stage longue durée": 15},
        # Pour un stage, l'éducation (0.25) prime sur l'expérience (0.10)
        # car les stagiaires n'ont pas encore de carrière longue.
        # La sémantique (0.40) est haute pour capter les projets académiques
        # et les centres d'intérêt pertinents.
        weight_overrides={"keyword": 0.15, "semantic": 0.40, "experience": 0.10,
                          "education": 0.25, "complexity": 0.05, "leadership": 0.05},
    ),
    Domain.TOURISM: DomainProfile(
        keywords=("tourisme", "voyage", "agence de voyage", "guide touristique",
                  "billetterie", "crm touristique", "gds", "amadeus"),
        indicators={"amadeus": 20, "gds": 15, "tourisme international": 20},
        weight_overrides={"keyword": 0.20, "semantic": 0.35, "experience": 0.25,
                          "education": 0.08, "complexity": 0.07, "leadership": 0.05},
    ),
    Domain.TRANSPORT: DomainProfile(
        keywords=("transport", "logistique", "chauffeur", "fret", "douane",
                  "transit", "affrètement", "tms", "déclaration en douane",
                  "incoterms", "fleet management"),
        indicators={"incoterms": 20, "tms": 20, "affrètement international": 20,
                    "douane": 15, "fleet management": 15},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.25,
                          "education": 0.08, "complexity": 0.07, "leadership": 0.05},
    ),
    Domain.SOCIAL: DomainProfile(
        keywords=("travail social", "ong", "humanitaire", "développement communautaire",
                  "action sociale", "volontariat", "projet social", "plaidoyer",
                  "protection sociale", "assistance aux personnes vulnérables"),
        indicators={"gestion de projet ong": 20, "plaidoyer": 15,
                    "financement bailleur": 20, "développement communautaire": 15},
        # Le travail social mise beaucoup sur la sémantique (0.40) car les valeurs,
        # la motivation et le contexte d'intervention sont difficiles à capter
        # avec des mots-clés stricts.
        weight_overrides={"keyword": 0.20, "semantic": 0.40, "experience": 0.18,
                          "education": 0.12, "complexity": 0.05, "leadership": 0.05},
    ),
    # ---- Domaines tech "étendus" : restent dans le pipeline tech
    #      mais avec des mots-clés et indicateurs spécialisés ----
    Domain.NETWORKS: DomainProfile(
        keywords=("réseau", "cisco", "firewall", "switch", "vpn", "infrastructure",
                  "cybersécurité", "pentest", "soc", "ids", "ips", "télécoms",
                  "5g", "lte", "sd-wan"),
        indicators={"pentest": 20, "soc": 20, "sd-wan": 20,
                    "certifié ccna": 20, "certifié cissp": 25},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.20,
                          "certification": 0.10, "complexity": 0.10,
                          "education": 0.03, "leadership": 0.02},
    ),
    Domain.ENGINEERING: DomainProfile(
        keywords=("mécanique", "électrique", "hydraulique", "conception", "autocad",
                  "solidworks", "catia", "bureau d'études", "simulation", "erd",
                  "maintenance préventive"),
        indicators={"catia": 20, "simulation cfd": 20, "certification iso": 15,
                    "projet r&d": 15},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.25,
                          "certification": 0.05, "complexity": 0.10,
                          "education": 0.03, "leadership": 0.02},
    ),
    Domain.SCIENCE: DomainProfile(
        keywords=("laboratoire", "protocole", "expérimentation", "publication",
                  "thèse", "r&d", "chimie", "biologie", "statistiques",
                  "matlab", "spss", "r", "python"),
        # Une publication indexée (25 pts) ou une thèse (20 pts) sont
        # des preuves très fortes d'expertise académique en recherche.
        indicators={"publication indexée": 25, "thèse": 20, "brevet": 20,
                    "financement recherche": 15},
        weight_overrides={"keyword": 0.20, "semantic": 0.30, "experience": 0.15,
                          "certification": 0.05, "complexity": 0.10,
                          "education": 0.15, "leadership": 0.05},
    ),
    Domain.ENERGY: DomainProfile(
        keywords=("pétrole", "mines", "forage", "géologie", "raffinage",
                  "énergie renouvelable", "solaire", "hydraulique", "reservoir",
                  "hse pétrolier", "offshore"),
        indicators={"offshore": 20, "reservoir engineering": 25,
                    "hse pétrolier": 20, "énergie solaire": 15},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.25,
                          "certification": 0.05, "complexity": 0.10,
                          "education": 0.03, "leadership": 0.02},
    ),
    Domain.INDUSTRY: DomainProfile(
        keywords=("production", "usine", "lean manufacturing", "5s", "kaizen",
                  "maintenance industrielle", "chaîne de montage", "plc",
                  "automatisme", "erp", "ordonnancement"),
        indicators={"lean manufacturing": 20, "automatisme plc": 20,
                    "tpm": 15, "six sigma": 25},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.25,
                          "certification": 0.05, "complexity": 0.10,
                          "education": 0.03, "leadership": 0.02},
    ),
    Domain.QHSE: DomainProfile(
        keywords=("hse", "qualité", "iso 9001", "iso 14001", "ohsas 18001",
                  "iso 45001", "audit qualité", "non-conformité", "plan de prévention",
                  "document unique", "analyse des risques"),
        indicators={"iso 9001": 20, "iso 45001": 20, "audit tierce partie": 20,
                    "analyse des risques": 15},
        weight_overrides={"keyword": 0.25, "semantic": 0.30, "experience": 0.20,
                          "certification": 0.10, "complexity": 0.10,
                          "education": 0.03, "leadership": 0.02},
    ),
}

# Profil de secours : utilisé quand aucun profil n'est défini pour un domaine.
# Reprend exactement DEFAULT_WEIGHTS sans modification.
_FALLBACK_PROFILE = DomainProfile(
    keywords=(),
    indicators={},
    weight_overrides={},
)


# -----------------------------------------------------------------------------
# CONSTANTES DU PIPELINE TECHNIQUE
# -----------------------------------------------------------------------------
# Ces constantes servent UNIQUEMENT pour les domaines TECH_DOMAINS.
# Pour les autres domaines, les profils (_DOMAIN_PROFILES) les remplacent.
#
# TECH_KEYWORDS : liste des technologies recherchées dans les CVs tech.
# _KW_PATTERNS  : version pré-compilée de ces mots-clés en expressions régulières.
#   → La compilation est faite une seule fois au chargement du module.
#   → \b...\b délimite les mots entiers (évite "java" de matcher "javascript").
#   → Les expressions avec espaces (ex: "spring boot") n'ont pas besoin de \b.
#
# CERTIFICATION_SCORES : points bonus pour certifications reconnues.
#   AWS, Scrum, Oracle → entre 30 et 35 pts chacune.
#
# LEADERSHIP_TERMS : mots qui indiquent un rôle d'encadrement.
#
# COMPLEXITY_INDICATORS : termes qui signalent des projets techniques complexes,
#   avec leur valeur en points. Ex: "kubernetes" = 20 pts, "ci/cd" = 10 pts.
#
# DEFAULT_REQUIRED_EXPERIENCE : si l'offre ne précise pas d'expérience requise,
#   on utilise 5 ans par défaut.
#
# DEFAULT_WEIGHTS : poids de base de chaque dimension dans le score final.
#   La somme vaut 1 (100%). Ces poids sont adaptatifs (voir plus bas).
# -----------------------------------------------------------------------------

TECH_KEYWORDS: tuple[str, ...] = (
    "spring boot", "node.js", "ci/cd",
    "python", "java", "spring", "react", "angular",
    "docker", "kubernetes", "aws", "azure", "gcp", "nestjs",
    "fastapi", "django", "graphql", "postgresql", "mongodb", "redis",
    "microservices", "scrum", "kafka", "typescript", "flutter",
    "tensorflow", "pytorch", "firebase",
)

_KW_PATTERNS: dict[str, re.Pattern] = {
    kw: re.compile(
        rf"\b{re.escape(kw)}\b" if " " not in kw else re.escape(kw),
        re.IGNORECASE,
    )
    for kw in TECH_KEYWORDS
}

CERTIFICATION_SCORES: dict[str, int] = {"aws": 35, "scrum": 30, "oracle": 35}

LEADERSHIP_TERMS: tuple[str, ...] = (
    "lead", "leader", "mentor", "management", "architect",
    "code review", "scrum", "encadrement",
)

COMPLEXITY_INDICATORS: dict[str, int] = {
    "microservices":     20,
    "kubernetes":        20,
    "distributed":       15,
    "millions":          15,
    "scalable":          15,
    "ci/cd":             10,
    "aws":               10,
    "architecture":      15,
    "real-time":         15,
    "event-driven":      15,
    "high availability": 20,
    "machine learning":  10,
    "tensorflow":        10,
    "pytorch":           10,
}

DEFAULT_REQUIRED_EXPERIENCE: int = 5

DEFAULT_WEIGHTS: dict[str, float] = {
    "keyword":       0.25,
    "semantic":      0.25,
    "experience":    0.25,
    "certification": 0.10,
    "complexity":    0.15,
    "education":     0.10,
    "leadership":    0.05,
}

# Boost appliqué à un poids quand un recruteur "like" un candidat
# dont cette dimension est forte (> 50).
_LIKE_BOOST    = 0.05

# Pénalité appliquée quand un recruteur "dislike" un candidat.
_DISLIKE_DECAY = 0.05

# Table de correspondance : nom de la dimension dans le résultat
# → nom de la clé dans le dictionnaire des poids.
# Utilisé par update_weights_from_feedback() pour modifier le bon poids.
_DIM_TO_WEIGHT: dict[str, str] = {
    "keyword_score":            "keyword",
    "semantic_score":           "semantic",
    "experience_score":         "experience",
    "certification_score":      "certification",
    "education_score":          "education",
    "leadership_score":         "leadership",
    "project_complexity_score": "complexity",
}

# Poids actifs en mémoire. Initialisés avec DEFAULT_WEIGHTS.
# Peuvent être mis à jour par update_weights_from_feedback().
# Variable globale : partagée entre tous les appels dans le même processus.
_active_weights: dict[str, float] = dict(DEFAULT_WEIGHTS)


# =============================================================================
# CLASSIFICATION AUTOMATIQUE DU DOMAINE
# =============================================================================

def classify_domain(cv_text: str, job_title: str, job_requirements: str) -> Domain:
    """
    Détermine automatiquement le domaine métier d'une offre/CV.

    Stratégie : on concatène le texte du CV, le titre du poste et les
    exigences en un seul texte normalisé (minuscules). On compte ensuite
    combien de signaux de _DOMAIN_DETECTION apparaissent pour chaque domaine.
    Le domaine avec le plus de correspondances l'emporte.

    En cas d'égalité, c'est le premier domaine rencontré dans _DOMAIN_DETECTION
    qui gagne. Comme les domaines TECH sont définis en premier dans l'enum et
    le dictionnaire, ils ont la priorité sur les offres ambiguës.

    Si aucun signal ne correspond (texte vide ou hors domaine connu),
    on retourne Domain.TECH par défaut (le domaine le plus générique).
    """
    combined = _norm(f"{cv_text} {job_title} {job_requirements}")

    best_domain  = Domain.TECH
    best_hits    = 0

    for domain, signals in _DOMAIN_DETECTION.items():
        hits = sum(1 for sig in signals if sig in combined)
        if hits > best_hits:
            best_hits   = hits
            best_domain = domain

    return best_domain


# =============================================================================
# FONCTIONS UTILITAIRES COMMUNES
# =============================================================================

def _norm(text: str | None) -> str:
    """Normalise un texte : minuscules + suppression des espaces en bord."""
    return (text or "").lower().strip()


def _clamp(value: float) -> float:
    """
    Contraint une valeur dans l'intervalle [0, 100] et arrondit à 2 décimales.
    Empêche les scores négatifs ou supérieurs à 100.
    """
    return round(max(0.0, min(value, 100.0)), 2)


def safe_list(value: Any) -> list[str]:
    """
    Convertit en toute sécurité une valeur quelconque en liste de chaînes.
    Gère les cas fréquents dans les données de CV :
      - None          → liste vide
      - str JSON      → parse et retourne la liste (ex: '["Python","Java"]')
      - str simple    → liste à un élément (ex: "Python")
      - list          → nettoyage et conversion en str
    """
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if item]
        except (json.JSONDecodeError, ValueError):
            return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item]
    return []


def safe_dict_list(value: Any) -> list[dict]:
    """
    Même logique que safe_list, mais pour des listes de dictionnaires.
    Utilisé pour work_history, projects, education (tableaux d'objets).
    Filtre les éléments qui ne sont pas des dicts (robustesse aux données mal formées).
    """
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except (json.JSONDecodeError, ValueError):
            return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


# =============================================================================
# CALCUL DES ANNÉES D'EXPÉRIENCE
# =============================================================================

def infer_experience_years(work_history: list[Any]) -> float:
    """
    Calcule le nombre total d'années d'expérience à partir de l'historique
    de travail d'un candidat.

    Pour chaque poste, on essaie dans cet ordre :
      1. Utiliser le champ "duration_months" s'il est déjà calculé.
      2. Calculer la durée à partir de "start_date" et "end_date".
         - Les dates peuvent être "YYYY-MM-DD", "YYYY-MM" ou "YYYY".
         - Si "end_date" est absent, on considère que le poste est actuel
           (date de fin = maintenant).
      3. Si les dates sont invalides, on ignore ce poste (continue).

    Retourne le total en années (arrondi à 1 décimale).
    Ex: 30 mois → 2.5 ans.
    """
    total_months = 0

    for item in work_history:
        if not isinstance(item, dict):
            continue

        duration = item.get("duration_months")
        if isinstance(duration, (int, float)) and duration > 0:
            total_months += int(duration)
            continue

        start = item.get("start_date")
        end   = item.get("end_date")

        try:
            if not start:
                continue
            # Normalise les dates au format "YYYY-MM" pour strptime
            start_str = start[:7] if len(start) >= 7 else f"{start[:4]}-01"
            end_str   = end[:7]   if (end and len(end) >= 7) else (
                        f"{end[:4]}-01" if (end and len(end) >= 4) else None)

            start_dt = datetime.strptime(start_str, "%Y-%m")
            end_dt   = datetime.strptime(end_str, "%Y-%m") if end_str else datetime.utcnow()

            months = (
                (end_dt.year - start_dt.year) * 12
                + end_dt.month
                - start_dt.month
            )
            total_months += max(months, 0)  # max(..., 0) empêche les durées négatives

        except (ValueError, TypeError):
            continue  # date mal formée → on ignore ce poste

    return round(total_months / 12, 1)


# =============================================================================
# CONSTRUCTION DES TEXTES POUR LE SCORING
# =============================================================================

def _build_cv_text(cv: dict[str, Any]) -> str:
    """
    Construit une représentation textuelle complète d'un CV pour l'analyse.

    Stratégie de récupération des données (ordre de priorité) :
      1. Champs directs du CV (work_history, projects, education, skills, etc.)
      2. Champ "ai_extracted_data" : données extraites par IA (JSON ou dict)
         → utilisé en fallback si les champs directs sont vides.

    Le texte final concatène (dans l'ordre) :
      - Résumé du profil
      - Poste actuel
      - Compétences (liste)
      - Certifications (liste)
      - Historique pro (titre + entreprise + description de chaque poste)
      - Projets (nom + tech + description + complexité)
      - Formation (diplôme + établissement)
      - Texte brut du CV (tronqué à 1000 caractères pour ne pas surcharger)

    Tout est normalisé (minuscules) via _norm() avant retour.
    """
    work_history = safe_dict_list(cv.get("work_history"))
    projects     = safe_dict_list(cv.get("projects"))
    education    = safe_dict_list(cv.get("education"))

    # Tentative de lecture de ai_extracted_data (peut être une str JSON ou un dict)
    ai_data: dict[str, Any] = {}
    raw_ai = cv.get("ai_extracted_data")
    if isinstance(raw_ai, str):
        try:
            ai_data = json.loads(raw_ai)
        except (json.JSONDecodeError, ValueError):
            pass
    elif isinstance(raw_ai, dict):
        ai_data = raw_ai

    # Fallback vers ai_extracted_data si les champs directs sont vides
    if not work_history:
        work_history = safe_dict_list(ai_data.get("work_history"))
    if not projects:
        projects = safe_dict_list(ai_data.get("projects"))
    if not education:
        education = safe_dict_list(ai_data.get("education"))

    skills         = safe_list(cv.get("skills"))         or safe_list(ai_data.get("skills"))
    certifications = safe_list(cv.get("certifications")) or safe_list(ai_data.get("certifications"))

    work_parts = []
    for job in work_history:
        work_parts.extend([
            str(job.get("title", "")),
            str(job.get("company", "")),
            str(job.get("description", "")),
        ])

    project_parts = []
    for project in projects:
        project_parts.extend([
            str(project.get("name", "")),
            str(project.get("tech", "")),
            str(project.get("description", "")),
            str(project.get("complexity", "")),
        ])

    education_parts = []
    for edu in education:
        education_parts.extend([
            str(edu.get("degree", "")),
            str(edu.get("institution", "")),
        ])

    summary          = cv.get("summary", "")          or ai_data.get("summary", "")
    current_position = cv.get("current_position", "") or ai_data.get("current_position", "")
    cv_raw_text      = cv.get("cv_raw_text", "")

    parts = [
        str(summary),
        str(current_position),
        " ".join(skills),
        " ".join(certifications),
        " ".join(work_parts),
        " ".join(project_parts),
        " ".join(education_parts),
        str(cv_raw_text)[:1000],  # Limité à 1000 chars pour les perfs
    ]

    return _norm(" ".join(filter(None, parts)))


def _build_job_text(title: str, requirements: str) -> str:
    """Construit le texte de l'offre d'emploi normalisé (titre + exigences)."""
    return _norm(f"{title} {requirements}")


# =============================================================================
# MATCHING PAR MOTS-CLÉS
# =============================================================================

def _extract_keywords_from_set(
    text: str,
    keywords: tuple[str, ...],
) -> set[str]:
    """
    Recherche des mots-clés dans un texte à partir d'un tuple arbitraire.

    Pour chaque mot-clé, compile un pattern regex à la volée :
      - Mot simple (sans espace) → \b...\b pour chercher des mots entiers.
        Ex: "java" ne matche pas dans "javascript".
      - Expression avec espace (ex: "supply chain") → recherche directe
        de la phrase (pas besoin de \b car les espaces servent de délimiteurs).

    Note : pour TECH_KEYWORDS, on utilise _extract_tech_keywords() qui est
    plus rapide car les patterns sont pré-compilés au niveau du module.
    Cette fonction est réservée aux keywords des profils de domaine.
    """
    result: set[str] = set()
    for kw in keywords:
        pat = re.compile(
            rf"\b{re.escape(kw)}\b" if " " not in kw else re.escape(kw),
            re.IGNORECASE,
        )
        if pat.search(text):
            result.add(kw)
    return result


def _extract_tech_keywords(text: str) -> set[str]:
    """
    Version rapide du matching pour les mots-clés tech.
    Utilise les patterns pré-compilés _KW_PATTERNS (module-level)
    au lieu de recompiler à chaque appel.
    """
    return {kw for kw, pat in _KW_PATTERNS.items() if pat.search(text)}


def _keyword_match(
    cv_text: str,
    job_text: str,
    keywords: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """
    Calcule le score de correspondance par mots-clés entre un CV et une offre.

    Logique :
      1. On extrait les mots-clés présents dans le CV → cv_kws
      2. On extrait les mots-clés présents dans l'offre → job_kws
      3. matched = intersection (présents dans les deux)
      4. missing = dans l'offre mais pas dans le CV (compétences manquantes)

    Score :
      - Si l'offre n'a aucun mot-clé reconnu → 50 (score neutre, pas pénalisant)
      - Sinon : (nb mots matchés / nb mots dans l'offre) * 100

    Si keywords=None → pipeline tech (TECH_KEYWORDS pré-compilés).
    Si keywords fournis → pipeline domaine (profil spécifique).

    Retourne : {"score": float, "matched": list, "missing": list}
    """
    if keywords is None:
        cv_kws  = _extract_tech_keywords(cv_text)
        job_kws = _extract_tech_keywords(job_text)
    else:
        cv_kws  = _extract_keywords_from_set(cv_text, keywords)
        job_kws = _extract_keywords_from_set(job_text, keywords)

    matched = sorted(cv_kws & job_kws)
    missing = sorted(job_kws - cv_kws)

    score = 50.0 if not job_kws else (len(matched) / len(job_kws)) * 100

    return {
        "score":   _clamp(score),
        "matched": matched,
        "missing": missing,
    }


# =============================================================================
# SCORE SÉMANTIQUE (SIMILARITÉ DE SENS)
# =============================================================================

def _semantic_score(cv_text: str, job_text: str) -> float:
    """
    Mesure la similarité sémantique entre le CV et l'offre d'emploi.

    Contrairement aux mots-clés (correspondance exacte), la similarité
    sémantique capture le "sens" : un CV qui parle de "développement backend"
    sera considéré proche d'une offre qui cherche un "ingénieur serveur",
    même si les mots sont différents.

    Algorithme :
      1. Tronque les textes (CV à 4000 chars, offre à 2000) pour limiter
         le temps de calcul et éviter de noyer le modèle.
      2. Le SentenceTransformer encode les deux textes en vecteurs numériques
         (des "embeddings" de 384 dimensions pour all-MiniLM-L6-v2).
         normalize_embeddings=True : les vecteurs sont normalisés (norme = 1),
         ce qui rend la cosine similarity équivalente au produit scalaire
         → calcul plus rapide.
      3. cosine_similarity calcule l'angle entre les deux vecteurs.
         Résultat entre -1 et 1 → multiplié par 100 pour avoir 0-100.

    En cas d'erreur (ex: modèle non chargé), retourne 0 sans faire planter.
    """
    cv_text  = cv_text[:4000]
    job_text = job_text[:2000]

    if not cv_text or not job_text:
        return 0.0

    try:
        model      = _get_model()
        embeddings = model.encode(
            [cv_text, job_text],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        return _clamp(float(similarity) * 100)

    except Exception as exc:
        print(f"[scoring] Semantic similarity error: {exc}")
        return 0.0


# =============================================================================
# SCORERS PAR DIMENSION
# =============================================================================

def _experience_score(candidate_years: float, required_years: float) -> float:
    """
    Score d'expérience : rapport entre ce que le candidat a et ce qui est requis.

    Ex: 3 ans d'expérience pour 5 ans requis → (3/5)*100 = 60.
        7 ans pour 5 requis → (7/5)*100 = 140 → clampé à 100.

    Si required_years <= 0 (non spécifié), score = 100 (pas de pénalité).
    """
    try:
        candidate_years = float(candidate_years or 0)
        required_years  = float(required_years  or 0)
        if required_years <= 0:
            return 100.0
        return _clamp((candidate_years / required_years) * 100)
    except Exception:
        return 0.0


def _certification_score(cv_text: str) -> float:
    """
    Score de certifications (pipeline TECH uniquement).
    Cherche "aws", "scrum", "oracle" dans le texte du CV.
    Additionne les points correspondants (AWS=35, Scrum=30, Oracle=35).
    Résultat clampé à 100.
    Note : non appelé pour les domaines non-tech (remplacé par _complexity_score).
    """
    total = sum(pts for cert, pts in CERTIFICATION_SCORES.items() if cert in cv_text)
    return _clamp(total)


def _education_score(cv_text: str) -> float:
    """
    Score de niveau d'études (simple détection par mots-clés).
    Hiérarchie décroissante :
      Doctorat/PhD → 100
      Master/Mastère → 90
      Licence/Bachelor/BTS/DUT → 75
      Autre (aucun diplôme détecté) → 50 (score de base, pas 0)

    Note : utilise des mots-clés en français et anglais pour la robustesse.
    """
    if "phd" in cv_text or "doctorate" in cv_text or "doctorat" in cv_text:
        return 100.0
    if "master" in cv_text or "mastère" in cv_text:
        return 90.0
    if "licence" in cv_text or "bachelor" in cv_text or "bts" in cv_text or "dut" in cv_text:
        return 75.0
    return 50.0


def _leadership_score(cv_text: str, extra_terms: tuple[str, ...] = ()) -> float:
    """
    Score de leadership : compte les termes d'encadrement dans le CV.

    Combine la liste globale LEADERSHIP_TERMS avec les termes spécifiques
    au domaine (extra_terms) fournis par le DomainProfile.

    +20 points par terme trouvé, clampé à 100.
    Ex: "lead" + "mentor" + "management" → 3 * 20 = 60 pts.
    """
    all_terms = LEADERSHIP_TERMS + extra_terms
    matches   = sum(1 for term in all_terms if term in cv_text)
    return _clamp(matches * 20)


def _complexity_score(
    cv_text: str,
    indicators: dict[str, int] | None = None,
) -> float:
    """
    Score de complexité / profondeur technique ou métier.

    Additionne les points de chaque indicateur trouvé dans le CV.

    Deux modes :
      - indicators=None  → utilise COMPLEXITY_INDICATORS (tech, ex: kubernetes=20)
      - indicators fourni → utilise les indicateurs du DomainProfile
        (ex: pour QHSE : "iso 9001"=20, "audit tierce partie"=20)

    Résultat clampé à 100.
    """
    source = indicators if indicators is not None else COMPLEXITY_INDICATORS
    score  = sum(pts for term, pts in source.items() if term in cv_text)
    return _clamp(score)


# =============================================================================
# GESTION DES POIDS
# =============================================================================

def _resolve_weights(
    base: dict[str, float],
    overrides: dict[str, float],
) -> dict[str, float]:
    """
    Fusionne les poids de base avec les surcharges du profil de domaine,
    puis normalise pour que la somme fasse exactement 1.

    Les clés présentes dans overrides remplacent celles de base.
    Les clés absentes de overrides conservent leurs valeurs de base.

    Exemple :
      base     = {"keyword": 0.20, "semantic": 0.30, ...}
      overrides= {"semantic": 0.40, "education": 0.15}
      merged   = {"keyword": 0.20, "semantic": 0.40, ..., "education": 0.15}
      → normalisé pour que sum = 1.
    """
    merged = {**base, **overrides}
    return _normalize_weights(merged)


# =============================================================================
# GESTION ADAPTATIVE DES POIDS (APPRENTISSAGE PAR FEEDBACK)
# =============================================================================
# Ce système permet aux recruteurs d'améliorer la pertinence des scores
# au fil du temps via des "like" et "dislike" sur les candidats proposés.
#
# Fonctionnement :
#   1. Les poids sont stockés en base de données (table app_config, clé "ats_weights").
#   2. Au démarrage, _load_weights() charge ces poids depuis la DB.
#      En absence de DB (tests, dev local), utilise _active_weights en mémoire.
#   3. Quand un recruteur like/dislike un candidat, update_weights_from_feedback()
#      ajuste les poids des dimensions qui ont le plus contribué au score.
#   4. Les nouveaux poids sont normalisés et sauvegardés en DB.
# =============================================================================

def _load_weights(supabase=None) -> dict[str, float]:
    """
    Charge les poids depuis Supabase (ou retourne les poids en mémoire si pas de DB).
    Valide que tous les clés de DEFAULT_WEIGHTS sont présentes avant d'utiliser
    les poids stockés (protection contre une DB corrompue ou incomplète).
    """
    if supabase is None:
        return dict(_active_weights)

    try:
        resp = (
            supabase.table("app_config")
            .select("value")
            .eq("key", "ats_weights")
            .single()
            .execute()
        )
        stored = resp.data and resp.data.get("value")
        if stored:
            if isinstance(stored, str):
                stored = json.loads(stored)
            if isinstance(stored, dict) and all(k in stored for k in DEFAULT_WEIGHTS):
                return {k: float(v) for k, v in stored.items()}
    except Exception as exc:
        print(f"[scoring] Failed to load weights from DB: {exc}")

    return dict(_active_weights)


def _save_weights(weights: dict[str, float], supabase=None) -> None:
    """
    Sauvegarde les poids dans Supabase via un UPSERT (insert ou update).
    on_conflict="key" : met à jour la ligne existante si "ats_weights" existe déjà.
    Silencieux si pas de DB (ne fait rien).
    """
    if supabase is None:
        return
    try:
        supabase.table("app_config").upsert(
            {"key": "ats_weights", "value": weights},
            on_conflict="key",
        ).execute()
    except Exception as exc:
        print(f"[scoring] Failed to save weights to DB: {exc}")


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """
    Normalise un dictionnaire de poids pour que leur somme vaille exactement 1.
    Si la somme est nulle ou négative (cas dégénéré), retourne DEFAULT_WEIGHTS.
    Chaque valeur est arrondie à 4 décimales.
    """
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(v / total, 4) for k, v in weights.items()}


def update_weights_from_feedback(
    *,
    supabase=None,
    candidate_id: str | None = None,  # Réservé pour l'audit (non utilisé ici)
    liked: bool = True,
    dimension_scores: dict[str, float] | None = None,
    feedback_data: dict[str, float] | None = None,
) -> None:
    """
    Adapte les poids de scoring en fonction du feedback d'un recruteur.

    Deux modes de mise à jour :

    Mode 1 — feedback_data (mise à jour directe) :
      Remplace directement les valeurs des poids spécifiés.
      Utile pour une interface d'administration qui permet de régler
      manuellement les poids.

    Mode 2 — dimension_scores + liked (apprentissage automatique) :
      Pour chaque dimension qui a un score > 50 (contribue positivement) :
        - liked=True  → augmente le poids de +0.05 (LIKE_BOOST)
        - liked=False → diminue le poids de -0.05 (DISLIKE_DECAY)
      Minimum: 0.01 (une dimension ne peut pas disparaître complètement).

    Après modification, les poids sont normalisés et sauvegardés.
    La variable globale _active_weights est mise à jour pour les appels suivants
    dans le même processus (évite de recharger la DB à chaque scoring).

    Note : * (keyword-only args) oblige à nommer tous les paramètres à l'appel,
    ce qui évite les erreurs de position dans une fonction à nombreux args.
    """
    global _active_weights

    weights = _load_weights(supabase)

    if feedback_data:
        for key, value in feedback_data.items():
            if key in weights:
                try:
                    weights[key] = float(value)
                except (TypeError, ValueError):
                    continue

    elif dimension_scores:
        delta = _LIKE_BOOST if liked else -_DISLIKE_DECAY
        for dim_key, dim_val in dimension_scores.items():
            if not isinstance(dim_val, (int, float)) or dim_val <= 50:
                continue
            weight_key = _DIM_TO_WEIGHT.get(dim_key)
            if weight_key and weight_key in weights:
                weights[weight_key] = max(0.01, weights[weight_key] + delta)

    weights         = _normalize_weights(weights)
    _active_weights = weights
    _save_weights(weights, supabase)


# =============================================================================
# MOTEUR DE SCORING PRINCIPAL
# =============================================================================

def compute_candidate_score(
    *,
    cv_data: dict[str, Any],
    job_title: str,
    job_requirements: str,
    required_experience: int = DEFAULT_REQUIRED_EXPERIENCE,
    supabase=None,
    domain: Domain | None = None,  # Si fourni, évite la classification auto
) -> dict[str, Any]:
    """
    Score un candidat par rapport à une offre d'emploi. C'est la fonction centrale.

    ÉTAPE 1 — Préparation
      - Charge les poids adaptatifs depuis la DB (ou mémoire).
      - Construit les textes normalisés du CV et de l'offre.
      - Détermine le domaine (fourni ou auto-détecté).
      - Récupère le profil du domaine et détermine s'il est tech ou non.
      - Fusionne les poids de base avec les surcharges du profil.

    ÉTAPE 2 — Calcul des 7 dimensions
      a) keyword_score      : % de mots-clés de l'offre présents dans le CV
      b) semantic_score     : similarité de sens CV ↔ offre (0-100)
      c) experience_score   : années candidat / années requises * 100
      d) certification_score: points pour certifications IT (TECH uniquement, sinon 0)
      e) education_score    : niveau d'études (50-100)
      f) leadership_score   : termes d'encadrement dans le CV
      g) project_complexity_score : indicateurs de projets complexes

    ÉTAPE 3 — Score final
      Somme pondérée des 7 dimensions avec les poids résolus.
      Résultat entre 0 et 100.

    ÉTAPE 4 — Confiance
      (semantic_score + keyword_score) / 200
      Mesure à quel point on "fait confiance" au score : si les deux dimensions
      les plus importantes sont faibles, le score global est moins fiable.

    Retourne un dict complet avec le score, la confiance, le domaine détecté,
    les mots-clés matchés/manquants, et le détail de toutes les dimensions.
    """
    base_weights = _load_weights(supabase)
    cv_text      = _build_cv_text(cv_data)
    job_text     = _build_job_text(job_title, job_requirements)

    # ── Détermination du domaine ─────────────────────────────────────────────
    if domain is None:
        domain = classify_domain(cv_text, job_title, job_requirements)

    profile     = _DOMAIN_PROFILES.get(domain, _FALLBACK_PROFILE)
    is_tech     = domain in TECH_DOMAINS
    weights     = _resolve_weights(base_weights, profile.weight_overrides)

    # ── Mots-clés ────────────────────────────────────────────────────────────
    if is_tech:
        kw = _keyword_match(cv_text, job_text)              # mots-clés tech
    else:
        kw = _keyword_match(cv_text, job_text, profile.keywords)  # mots-clés du domaine

    # ── Sémantique ───────────────────────────────────────────────────────────
    sem_score = _semantic_score(cv_text, job_text)

    # ── Certifications ───────────────────────────────────────────────────────
    # Les certifications IT (AWS, Scrum, Oracle) n'ont pas de sens pour
    # un comptable ou un médecin → score = 0 pour les domaines non-tech.
    # Les profils non-tech ont déjà un weight_override qui met "certification"
    # à 0 ou très bas, donc cette valeur 0 n'impacte pas le score final.
    cert_score = _certification_score(cv_text) if is_tech else 0.0

    # ── Éducation ────────────────────────────────────────────────────────────
    edu_score = _education_score(cv_text)

    # ── Leadership ───────────────────────────────────────────────────────────
    lead_score = _leadership_score(cv_text, profile.leadership_terms)

    # ── Complexité ───────────────────────────────────────────────────────────
    if is_tech:
        complex_score = _complexity_score(cv_text)              # indicateurs tech globaux
    else:
        complex_score = _complexity_score(cv_text, profile.indicators)  # indicateurs domaine

    # ── Expérience ───────────────────────────────────────────────────────────
    # Même logique de fallback que pour les autres données : champ direct → ai_extracted_data.
    ai_data: dict[str, Any] = {}
    raw_ai = cv_data.get("ai_extracted_data")
    if isinstance(raw_ai, str):
        try:
            ai_data = json.loads(raw_ai)
        except (json.JSONDecodeError, ValueError):
            pass
    elif isinstance(raw_ai, dict):
        ai_data = raw_ai

    work_history = (
        safe_dict_list(cv_data.get("work_history"))
        or safe_dict_list(ai_data.get("work_history"))
    )
    candidate_years = (
        cv_data.get("experience_years")
        or ai_data.get("experience_years")
        or infer_experience_years(work_history)
        or 0
    )
    exp_score = _experience_score(candidate_years, required_experience)

    # ── Somme pondérée ───────────────────────────────────────────────────────
    dimensions = {
        "keyword_score":            kw["score"],
        "semantic_score":           sem_score,
        "experience_score":         exp_score,
        "certification_score":      cert_score,
        "education_score":          edu_score,
        "leadership_score":         lead_score,
        "project_complexity_score": complex_score,
    }

    final_score = _clamp(
        kw["score"]     * weights["keyword"]
        + sem_score     * weights["semantic"]
        + exp_score     * weights["experience"]
        + cert_score    * weights["certification"]
        + complex_score * weights["complexity"]
        + edu_score     * weights["education"]
        + lead_score    * weights["leadership"]
    )

    return {
        "score":            final_score,
        "confidence":       round((sem_score + kw["score"]) / 200, 2),
        "domain":           domain.value,
        "reasoning": (
            f"Domain={domain.value}, "
            f"Semantic={sem_score:.1f}, Keywords={kw['score']:.1f}, "
            f"Experience={exp_score:.1f}, Certifications={cert_score:.1f}, "
            f"Education={edu_score:.1f}, Leadership={lead_score:.1f}, "
            f"Complexity={complex_score:.1f}"
        ),
        "matched_keywords": kw["matched"],
        "missing_keywords": kw["missing"],
        "dimension_scores": dimensions,
    }


# =============================================================================
# VERSION ASYNCHRONE (pour les serveurs web / APIs)
# =============================================================================

async def compute_candidate_score_async(
    *,
    cv_data: dict[str, Any],
    job_title: str,
    job_requirements: str,
    required_experience: int = DEFAULT_REQUIRED_EXPERIENCE,
    supabase=None,
    domain: Domain | None = None,
) -> dict[str, Any]:
    """
    Version asynchrone de compute_candidate_score.

    compute_candidate_score est une fonction synchrone (bloquante) car
    le modèle SentenceTransformer fait du calcul intensif CPU/GPU.
    Dans un serveur async (FastAPI, etc.), exécuter du code bloquant
    directement dans la boucle d'événements gèlerait tous les autres clients.

    Solution : run_in_executor() délègue l'exécution à un ThreadPoolExecutor
    (thread séparé), libérant la boucle async pendant le calcul.
    Le "await" reprend quand le thread a fini.

    lambda : nécessaire pour passer les arguments nommés (keyword args)
    à une fonction exécutée via run_in_executor (qui n'accepte que les callables
    sans arguments ou avec args positionnels).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: compute_candidate_score(
            cv_data=cv_data,
            job_title=job_title,
            job_requirements=job_requirements,
            required_experience=required_experience,
            supabase=supabase,
            domain=domain,
        ),
    )


# =============================================================================
# SCORING EN LOT (PLUSIEURS CANDIDATS À LA FOIS)
# =============================================================================

def batch_score_candidates(
    candidates: list[dict[str, Any]],
    *,
    job_title: str,
    job_requirements: str,
    required_experience: int = DEFAULT_REQUIRED_EXPERIENCE,
    supabase=None,
    domain: Domain | None = None,
) -> list[dict[str, Any]]:
    """
    Score une liste de candidats pour une même offre et retourne les résultats
    triés du meilleur au moins bon (reverse=True = ordre décroissant).

    Chaque résultat contient le CV original ("cv") + toutes les clés de
    compute_candidate_score (score, domain, reasoning, etc.).

    Version synchrone : les candidats sont traités séquentiellement.
    Pour de grandes listes (50+ candidats), préférer la version async
    qui parallélise les calculs.
    """
    results = [
        {
            "cv": cv,
            **compute_candidate_score(
                cv_data=cv,
                job_title=job_title,
                job_requirements=job_requirements,
                required_experience=required_experience,
                supabase=supabase,
                domain=domain,
            ),
        }
        for cv in candidates
    ]
    return sorted(results, key=lambda r: r["score"], reverse=True)


async def batch_score_candidates_async(
    candidates: list[dict[str, Any]],
    *,
    job_title: str,
    job_requirements: str,
    required_experience: int = DEFAULT_REQUIRED_EXPERIENCE,
    supabase=None,
    domain: Domain | None = None,
) -> list[dict[str, Any]]:
    """
    Version asynchrone du scoring en lot.

    asyncio.gather() lance TOUS les scorings en parallèle (concurrence, pas
    forcément vraie parallélisation CPU, mais les threads de run_in_executor
    tournent en parallèle grâce au GIL Python qui se relâche pour le code C).
    Le résultat est une liste dans le même ordre que les tâches créées.

    zip(candidates, scores) relie chaque CV à son score pour construire
    le résultat final, qui est ensuite trié par score décroissant.

    Avantage par rapport à la version sync : sur 100 candidats, au lieu
    d'attendre score_1 + score_2 + ... + score_100, on attend max(tous les scores).
    """
    tasks = [
        compute_candidate_score_async(
            cv_data=cv,
            job_title=job_title,
            job_requirements=job_requirements,
            required_experience=required_experience,
            supabase=supabase,
            domain=domain,
        )
        for cv in candidates
    ]
    scores  = await asyncio.gather(*tasks)
    results = [{"cv": cv, **score} for cv, score in zip(candidates, scores)]
    return sorted(results, key=lambda r: r["score"], reverse=True)