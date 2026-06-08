# Service de Scoring

Documentation technique du moteur de scoring de CVs, conçu pour le marché francophone africain.

---

## Vue d'ensemble

Le service de scoring évalue automatiquement la pertinence d'un candidat par rapport à un poste. Il attribue un **score final entre 0 et 100** en combinant neuf dimensions d'évaluation, pondérées selon le niveau hiérarchique du poste visé.

Le scoring se déclenche dans trois situations :

- Un CV est uploadé manuellement par un recruteur
- Un CV est synchronisé depuis Google Drive
- Un recruteur relance le scoring via l'API (`POST /candidates/{id}/score`)

---

## Architecture générale

```
CV brut (PDF)
     │
     ▼
Extraction texte (cv_parser)
     │
     ▼
Analyse IA (ai_service / Gemini)
     │
     ▼
Scoring hiérarchique (scoring_service)
     ├── Détection du domaine métier
     ├── Détection du niveau hiérarchique
     ├── Calcul des 8 dimensions
     ├── Pénalités de carence
     └── Score final (0–100)
     │
     ▼
Sauvegarde en base (Supabase)
```

---

## Étape 1 — Détection automatique du contexte

Avant tout calcul, le service identifie deux paramètres clés à partir du titre du poste.

### Niveau hiérarchique (`HierarchyLevel`)

Quatre niveaux sont reconnus, par ordre de priorité décroissante :

| Niveau | Exemples de titres reconnus |
|---|---|
| `DIRECTION` | Directeur Général, CEO, PDG, VP, Chief... |
| `MANAGER_SENIOR` | Responsable, Chef de département, Head of, Senior Manager... |
| `MANAGER_INTERMEDIAIRE` | Chef de service, Superviseur, Team Lead, Coordinateur... |
| `COLLABORATEUR` | Analyste, Technicien, Assistant, Agent, Junior... |

Le niveau détecté détermine les **poids de chaque dimension** et les **seuils d'éligibilité** du candidat.

### Domaine métier (`Domain`)

27 domaines sont couverts : Tech, Finance, RH, Logistique, Construction, Santé, Agriculture, Juridique, etc.

Le domaine est détecté par correspondance de mots-clés dans le titre et la description du poste. Il oriente les listes de compétences de référence utilisées pour le scoring.

---

## Étape 2 — Les 8 dimensions de scoring

Chaque dimension produit un score entre **0 et 1**.

### 1. Expérience (`experience`)

Compare les années d'expérience détectées dans le CV aux années requises par le poste.

- Le service extrait les mentions du type *"10 ans d'expérience"*, *"5 years"*, etc.
- Si le candidat a exactement le nombre d'années requis → score 0.7 minimum
- Si le candidat dépasse le double des années requises → score 1.0
- Si le candidat est en dessous du seuil minimum pour le niveau → pénalité de 50 %

### 2. Éducation (`education`)

Détecte le niveau de diplôme le plus élevé mentionné dans le CV et le compare au niveau requis par le niveau hiérarchique du poste.

Niveaux reconnus (par ordre croissant) :

```
CAP/BEP → Bac → BTS/DUT → Licence → Maîtrise → Master/MBA/Ingénieur → Doctorat
```

Exemples de diplômes reconnus : bac, licence, bachelor, master, MBA, ingénieur, diplôme d'ingénieur, grande école, doctorat, PhD.

### 3. Certifications (`certifications`)

Détecte les certifications professionnelles dans le texte du CV. Le matching est insensible aux accents et aux variantes orthographiques.

Certifications reconnues (exemples) :

| Certification | Domaine | Poids |
|---|---|---|
| OHADA | Juridique | 1.5 |
| CFA | Finance | 1.5 |
| PMP | Conseil | 1.2 |
| IFRS, ACCA, CPA | Finance | 1.3 |
| AWS, Azure, GCP | Tech | 0.9–1.0 |
| ISO 9001, 14001, 45001 | Qualité/HSE | 1.0 |
| HACCP | Agriculture | 1.0 |
| TOEIC, TOEFL, IELTS | Langues | 0.5 |

Un bonus est appliqué si la certification correspond au domaine du poste, et si son niveau est élevé pour un poste senior.

### 4. Sémantique (`semantic`)

Mesure la proximité de contenu entre le CV et la description du poste via deux signaux :

- **Jaccard (40 %)** : proportion de mots communs entre le CV et la fiche de poste
- **Couverture de compétences domaine (60 %)** : proportion des compétences de référence du domaine présentes dans le CV

> En l'absence du modèle sémantique (MiniLM), ce calcul utilise un fallback lexical normalisé. Les scores sont donc plus bas qu'avec un vrai modèle d'embeddings.

### 5. Mots-clés (`keywords`)

Vérifie la présence de mots-clés spécifiques dans le CV.

- Si des mots-clés sont explicitement définis dans le poste → matching direct
- Sinon → fallback sur les compétences de référence du domaine (plafonné à 12 termes)

Un coefficient de 1.5× est appliqué au ratio de matching pour compenser la sévérité du calcul.

### 6. Leadership (`leadership`)

Évalue les signaux de management dans le texte du CV. **Ne s'applique qu'aux niveaux MANAGER_INTERMEDIAIRE, MANAGER_SENIOR et DIRECTION.**

Deux sources de signal :

- **Verbes d'action (60 %)** : dirigé, piloté, managé, supervisé, encadré, led, oversaw, spearheaded, etc.
- **Titres passés (40 %)** : si les postes précédents contiennent des marqueurs hiérarchiques

Exemples de verbes reconnus : *dirigé, piloté, managé, encadré, restructuré, fondé, coordonné, led, managed, headed, directed, spearheaded, mentored...*

Pour les postes `COLLABORATEUR`, cette dimension retourne automatiquement 1.0 (non applicable).

### 7. Qualité linguistique (`language`)

Évalue la qualité rédactionnelle du CV sur trois critères :

- **Richesse lexicale (30 %)** : ratio mots uniques / total des mots
- **Structure du document (30 %)** : présence des sections attendues (Expérience, Formation, Compétences, Langues, etc.)
- **Longueur adéquate (20 %)** : le CV doit contenir au minimum ~200 mots pour un score plein
- **Score de base (20 %)** : bonus de présence

La langue détectée (français, anglais, mixte) est enregistrée mais ne pénalise pas un CV bien rédigé en anglais.

### 8. Complexité du parcours (`complexity`)

Mesure la diversité et la profondeur du profil :

- **Diversité (base)** : nombre de domaines métier différents touchés dans le CV
- **Multiplicateur par niveau** : 0.8× pour Collaborateur, 1.0× pour Manager intermédiaire, 1.2× pour Manager senior, 1.5× pour Direction
- **Couverture du domaine principal (40 %)** : bonus si les compétences clés du domaine cible sont bien représentées

---

## Étape 3 — Poids par niveau hiérarchique

Les 8 dimensions ne contribuent pas de façon égale selon le niveau du poste. Voici la répartition des poids :

| Dimension | Collaborateur | Manager inter. | Manager senior | Direction |
|---|---|---|---|---|
| Expérience | 20 % | 22 % | 25 % | 20 % |
| Éducation | 15 % | 12 % | 10 % | 10 % |
| Certifications | 10 % | 8 % | 8 % | 5 % |
| Sémantique | 15 % | 18 % | 15 % | 12 % |
| Mots-clés | 15 % | 12 % | 8 % | 5 % |
| Leadership | 0 % | 10 % | 15 % | **25 %** |
| Langue | 5 % | 5 % | 7 % | 10 % |
| Complexité | 10 % | 8 % | 7 % | 8 % |

Le leadership prend une place prépondérante pour les profils de Direction (25 %), tandis que les mots-clés et la sémantique sont davantage valorisés pour les profils opérationnels.

---

## Étape 4 — Pénalités de carence

En plus de l'agrégation pondérée, des **pénalités** s'appliquent si certaines dimensions critiques tombent en dessous d'un seuil minimal.

| Dimension | Seuil | Pénalité max | Courbe |
|---|---|---|---|
| Expérience | 0.15 | 40 % | Exponentielle |
| Éducation | 0.10 | 25 % | Palier (step) |
| Certifications | 0.05 | 15 % | Linéaire |
| Leadership | 0.10 | 20 % | Linéaire |
| Langue | 0.10 | 10 % | Linéaire |

La pénalité totale est plafonnée à **40 %** du score, pour éviter qu'un candidat avec un seul point faible soit éliminé sur l'ensemble.

> **Note :** La pénalité sur les certifications ne s'active que pour les postes `MANAGER_SENIOR` (seul niveau où `require_certifications = True`).

---

## Étape 5 — Score final

```
Score final = (somme pondérée des 8 dimensions) - pénalités + bonus de résilience
```

Le bonus de résilience (`w_penalty × (1 - pénalité)`) atténue légèrement l'impact des pénalités pour les candidats globalement solides.

Le résultat est ensuite multiplié par 100 et arrondi à deux décimales pour l'affichage (échelle 0–100).

---

## Fallback : scoring sans poste actif

Quand aucun poste actif n'est disponible (lors d'une synchronisation Drive ou d'un upload sans job_id), le service génère une **fiche de poste synthétique** à partir du contenu du CV lui-même :

1. Le titre du poste actuel du candidat est utilisé comme intitulé
2. Ses compétences, expériences et projets forment la description
3. Le scoring tourne contre cette JD synthétique
4. Les scores `keyword` et `semantic` sont légèrement atténués (×0.85 et ×0.80) pour éviter une inflation artificielle due à l'auto-référencement

Ce mode produit un **score de qualité CV** plutôt qu'un score de correspondance poste.

---

## Interface de compatibilité

La fonction principale exposée à l'application est `compute_candidate_score()` :

```python
result = compute_candidate_score(
    cv_data={"raw_text": "...", "skills": [...], "work_history": [...]},
    job_title="Responsable Achats",
    job_requirements="...",
)

# result contient :
# {
#   "score": 72.45,               # 0–100
#   "confidence": 72.45,
#   "domain": "logistics",
#   "hierarchy_level": "manager_senior",
#   "reasoning": "...",
#   "matched_keywords": [...],
#   "dimension_scores": {
#       "experience": 0.85,
#       "education": 0.70,
#       ...
#       "keyword_score": 0.60,    # alias frontend ScorePanel.jsx
#       "semantic_score": 0.55,
#       ...
#   }
# }
```

> **Important :** `cv_data` doit impérativement contenir la clé `raw_text` (texte brut complet du CV). Sans elle, les dimensions sémantique, mots-clés, éducation et certifications ne peuvent pas analyser le document correctement et retourneront des scores très faibles.

---

## Apprentissage par feedback

Le service intègre une boucle d'apprentissage simple (`update_weights_from_feedback`). Les recruteurs peuvent soumettre des notes réelles sur les candidats (embauché, refusé, score réel), et les poids des dimensions sont ajustés par descente de gradient pour rapprocher les prédictions des décisions réelles.

```python
feedback = [
    FeedbackRecord(candidate_id="...", predicted_score=0.72, actual_rating=0.90, actual_outcome="hired"),
    FeedbackRecord(candidate_id="...", predicted_score=0.65, actual_rating=0.35, actual_outcome="rejected"),
]
new_weights = update_weights_from_feedback(current_weights, feedback, learning_rate=0.01)
```

---

## Domaines couverts

27 domaines métier adaptés au tissu économique ivoirien et francophone :

Tech · Finance · RH · Agriculture · Construction · Santé · Juridique · Éducation · Logistique · Marketing · Commerce · Télécoms · Énergie · Mines · Hôtellerie · Médias · Assurance · Immobilier · Conseil · Administration publique · ONG · Pharma · Distribution · Transport · Environnement · Artisanat · Sécurité

---

## Fichiers concernés

| Fichier | Rôle |
|---|---|
| `app/services/scoring_service.py` | Moteur de scoring complet |
| `app/tasks/cv_processing.py` | Pipeline de traitement CV (upload manuel) |
| `app/tasks/drive_sync.py` | Pipeline de synchronisation Google Drive |
| `app/api/v1/candidates.py` | Endpoints API (score, backfill) |
