// frontend/src/utils/domainClassifier.js
// ─────────────────────────────────────────────────────────────────────────────
// Classifies a candidate into one of the 28 sector folders based on keywords
// found in their job title / current position.
//
// Usage:
//   import { classifyCandidate } from "../utils/domainClassifier";
//   const domain = classifyCandidate(candidate); // returns a JOB_DOMAINS value
// ─────────────────────────────────────────────────────────────────────────────

// Each rule: { domain, keywords[] }
// Keywords are matched case-insensitively anywhere in the position string.
// Rules are evaluated in order — first match wins.
// More specific / niche terms should come before broader ones.

const CLASSIFICATION_RULES = [
  // ── Informatique & Développement logiciel ─────────────────────────────────
  {
    domain: "informatique_dev",
    keywords: [
      "data scientist", "data science", "machine learning", "deep learning",
      "ml engineer", "ai engineer", "intelligence artificielle",
      "nlp", "computer vision", "data analyst", "data engineer",
      "business intelligence", "bi developer", "bi analyst",
      "frontend", "front-end", "front end",
      "backend", "back-end", "back end",
      "fullstack", "full-stack", "full stack",
      "développeur", "developpeur", "developer", "dev ",
      "software engineer", "ingénieur logiciel", "ingenieur logiciel",
      "web developer", "développeur web", "web dev",
      "react", "angular", "vue", "nextjs", "node", "nodejs",
      "python developer", "java developer", "php developer",
      "mobile developer", "android developer", "ios developer", "flutter",
      "devops", "sre", "site reliability",
      "cloud engineer", "cloud architect",
      "database administrator", "dba", "administrateur base",
      "qa engineer", "quality assurance engineer", "test engineer",
      "scrum master", "agile coach",
      "informatique", "it support", "technicien informatique",
      "administrateur système", "sysadmin", "system administrator",
      "architecte logiciel", "software architect",
      "développeur mobile", "développeur fullstack", "Computer Science","Computer Engineer", "Computer Scientist",
    ],
  },

  // ── Réseaux, Télécoms & Cybersécurité ────────────────────────────────────
  {
    domain: "reseaux_telecoms_cyber",
    keywords: [
      "cybersécurité", "cybersecurity", "sécurité informatique",
      "réseau", "reseau", "network engineer", "network administrator",
      "télécom", "telecom", "télécommunication", "telecommunication",
      "ingénieur réseau", "administrateur réseau",
      "firewall", "pentest", "penetration test", "ethical hacker",
      "soc analyst", "security analyst", "analyste sécurité",
      "cisco", "ccna", "ccnp", "noc engineer",
    ],
  },

  // ── Construction & BTP ────────────────────────────────────────────────────
  {
    domain: "construction_btp",
    keywords: [
      "génie civil", "genie civil",
      "conducteur de travaux", "conductrice de travaux",
      "chef de chantier", "chef chantier",
      "ingénieur btp", "ingenieur btp",
      "architecte", "architect",
      "topographe", "surveyor",
      "manœuvre", "manouvre", "maçon", "mason",
      "plombier", "plomberie", "electricien bâtiment",
      "charpentier", "couvreur", "carreleur", "peintre bâtiment",
      "métreur", "dessinateur btp", "projeteur btp",
      "btp", "bâtiment", "batiment", "construction",
      "travaux publics", "ouvrier", "chantier",
      "ingénieur géotechnique", "ingénieur structure",
      "technicien btp", "technicien génie civil", "conducteur de travaux",
      "conductrice de travaux", "chef de chantier", "chef chantier","conducteur","conductrice"
    ],
  },

  // ── Ingénierie & Techniques ───────────────────────────────────────────────
  {
    domain: "ingenierie_techniques",
    keywords: [
      "ingénieur mécanique", "ingenieur mecanique", "mechanical engineer",
      "ingénieur électrique", "electrical engineer",
      "ingénieur industriel", "industrial engineer",
      "ingénieur process", "process engineer",
      "ingénieur production", "production engineer",
      "ingénieur qualité", "quality engineer",
      "ingénieur maintenance", "maintenance engineer",
      "technicien de maintenance", "technicien maintenance",
      "ingénieur projet", "project engineer",
      "dessinateur industriel", "dessinateur mécanique",
      "automaticien", "automatisation", "automation engineer",
      "électromécanique", "electromecanique",
      "génie mécanique", "mécanique", "mecanique",
      "métrologie", "bureau d'études",
    ],
  },

  // ── Énergie, Mines & Pétrole ──────────────────────────────────────────────
  {
    domain: "energie_mines_petrole",
    keywords: [
      "pétrole", "petrole", "oil", "gas", "gaz naturel",
      "mine", "minier", "mining", "géologue", "geologue",
      "énergie renouvelable", "energie renouvelable", "solar", "solaire",
      "électricité", "electricite", "energy engineer", "ingénieur énergie",
      "hse mines", "technicien minier", "forage", "drilling",
      "raffinerie", "pipeline",
    ],
  },

  // ── Finance & Comptabilité ────────────────────────────────────────────────
  {
    domain: "comptabilite_finance",
    keywords: [
      "comptable", "comptabilité", "comptabilite", "accountant", "accounting",
      "financier", "finance", "directeur financier", "cfo",
      "contrôleur de gestion", "controleur de gestion", "controller",
      "auditeur", "audit", "auditor",
      "trésorier", "tresorier", "treasurer",
      "fiscaliste", "fiscalité", "tax",
      "analyste financier", "financial analyst",
      "credit analyst", "analyste crédit",
      "expert comptable",
    ],
  },

  // ── Banque & Assurance ────────────────────────────────────────────────────
  {
    domain: "banque_assurance",
    keywords: [
      "banque", "banking", "banker", "banquier",
      "assurance", "insurance", "actuaire", "actuary",
      "chargé de clientèle", "charge de clientele",
      "conseiller bancaire", "gestionnaire de patrimoine",
      "risk manager", "gestionnaire risque",
      "analyste risque", "underwriter",
      "microfinance", "crédit manager",
    ],
  },

  // ── Commercial & Vente ────────────────────────────────────────────────────
  {
    domain: "commercial_vente",
    keywords: [
      "commercial", "commerciale", "sales", "vendeur", "vendeuse",
      "account manager", "account executive",
      "business developer", "business development",
      "représentant commercial", "technico-commercial",
      "responsable commercial", "directeur commercial",
      "key account", "kam", "chef de vente",
    ],
  },

  // ── Marketing & Communication ─────────────────────────────────────────────
  {
    domain: "marketing_communication",
    keywords: [
      "marketing", "communication", "community manager",
      "digital marketing", "growth hacker", "growth marketer",
      "seo", "sem", "content creator", "content manager",
      "social media", "brand manager", "chef de produit",
      "chargé de communication", "relations publiques",
      "publicité", "advertising", "media planner",
      "responsable marketing",
    ],
  },

  // ── Ressources Humaines ───────────────────────────────────────────────────
  {
    domain: "ressources_humaines",
    keywords: [
      "ressources humaines", "rh ", "hr ", "human resources",
      "recruteur", "recruiter", "talent acquisition",
      "chargé rh", "charge rh", "responsable rh",
      "drh", "directeur rh", "hr manager",
      "paie", "payroll", "gestionnaire paie",
      "formation professionnelle", "learning", "l&d",
      "relations sociales", "droit social",
    ],
  },

  // ── Logistique & Transport ────────────────────────────────────────────────
  {
    domain: "transport_logistique",
    keywords: [
      "logistique", "logistics", "supply chain",
      "transport", "transporteur", "chauffeur",
      "livreur", "coursier", "dispatcher",
      "responsable logistique", "directeur logistique",
      "gestionnaire stock", "magasinier", "warehouse",
      "import export", "douane", "freight",
      "chef de quai", "planificateur",
    ],
  },

  // ── Achats & Supply Chain ─────────────────────────────────────────────────
  {
    domain: "achats_supply_chain",
    keywords: [
      "acheteur", "achats", "purchasing", "procurement",
      "approvisionneur", "approvisionnement",
      "supply chain manager", "gestionnaire achats",
      "responsable achats",
    ],
  },

  // ── Administration & Secrétariat ─────────────────────────────────────────
  {
    domain: "administration_secretariat",
    keywords: [
      "secrétaire", "secretaire", "secretary",
      "assistant administratif", "assistante administrative",
      "office manager", "assistant de direction",
      "réceptionniste", "receptionniste", "hôtesse d'accueil",
      "agent administratif", "gestionnaire administratif",
    ],
  },

  // ── Agriculture & Agroalimentaire ────────────────────────────────────────
  {
    domain: "agriculture_agroalimentaire",
    keywords: [
      "agriculture", "agriculteur", "agronome", "agronomie",
      "agroalimentaire", "agro-alimentaire",
      "ingénieur agricole", "technicien agricole",
      "élevage", "elevage", "vétérinaire", "veterinaire",
      "pêche", "peche", "forestier",
    ],
  },

  // ── Santé & Médical ───────────────────────────────────────────────────────
  {
    domain: "sante_medical",
    keywords: [
      "médecin", "medecin", "doctor", "physician",
      "infirmier", "infirmière", "nurse",
      "pharmacien", "pharmacienne", "pharmacist",
      "chirurgien", "surgeon",
      "laborantin", "biologiste", "biologist",
      "kinésithérapeute", "physiothérapeute",
      "sage-femme", "gynécologue", "pédiatre",
      "santé", "sante", "health", "médical", "medical",
      "dentiste", "opticien",
    ],
  },

  // ── Éducation & Formation ─────────────────────────────────────────────────
  {
    domain: "education_formation",
    keywords: [
      "enseignant", "professeur", "teacher", "instructor",
      "formateur", "formatrice", "trainer",
      "éducateur", "educateur", "education",
      "directeur école", "proviseur",
      "conseiller pédagogique", "curriculum",
    ],
  },

  // ── Droit & Juridique ────────────────────────────────────────────────────
  {
    domain: "droit_juridique",
    keywords: [
      "juriste", "avocat", "lawyer", "attorney",
      "notaire", "huissier", "magistrat",
      "conseiller juridique", "legal counsel",
      "droit", "juridique", "legal",
      "compliance", "conformité",
    ],
  },

  // ── QHSE ─────────────────────────────────────────────────────────────────
  {
    domain: "qhse",
    keywords: [
      "qhse", "hse", "qualité hygiène sécurité",
      "responsable qhse", "ingénieur qhse",
      "sécurité au travail", "sst",
      "iso", "qualité", "quality manager",
      "environment manager", "environnement",
    ],
  },

  // ── Art, Culture & Design ─────────────────────────────────────────────────
  {
    domain: "art_culture_design",
    keywords: [
      "designer", "ui designer", "ux designer", "graphiste",
      "graphic designer", "motion designer",
      "illustrateur", "photographe", "photographer",
      "artiste", "artist", "créatif",
      "directeur artistique", "art director",
      "vidéaste", "monteur vidéo", "video editor",
    ],
  },

  // ── Journalisme & Médias ──────────────────────────────────────────────────
  {
    domain: "journalisme_medias",
    keywords: [
      "journaliste", "journalist", "reporter",
      "rédacteur", "redacteur", "editor",
      "présentateur", "animateur radio", "animateur tv",
      "correspondant", "pigiste",
      "media", "presse",
    ],
  },

  // ── Hôtellerie & Restauration ─────────────────────────────────────────────
  {
    domain: "hotellerie_restauration",
    keywords: [
      "hôtellerie", "hotellerie", "hotel",
      "restauration", "restaurant",
      "cuisinier", "chef cuisinier", "chef de cuisine",
      "serveur", "barman", "réceptionniste hôtel",
      "directeur hôtel", "responsable hébergement",
      "food and beverage", "f&b",
    ],
  },

  // ── Immobilier ────────────────────────────────────────────────────────────
  {
    domain: "immobilier",
    keywords: [
      "immobilier", "real estate", "agent immobilier",
      "promoteur immobilier", "gestionnaire immobilier",
      "administrateur de biens", "syndic",
    ],
  },

  // ── Sciences & Recherche ──────────────────────────────────────────────────
  {
    domain: "sciences_recherche",
    keywords: [
      "chercheur", "researcher", "research",
      "scientifique", "scientist", "laboratoire",
      "chimiste", "physicien", "biologiste moléculaire",
      "r&d", "recherche et développement",
      "doctorant", "post-doc",
    ],
  },

  // ── Production & Industrie ────────────────────────────────────────────────
  {
    domain: "production_industrie",
    keywords: [
      "opérateur de production", "operateur production",
      "responsable production", "chef de production",
      "technicien de production", "contremaître",
      "industrie", "usine", "manufacturing",
      "planificateur production", "lean", "six sigma",
    ],
  },

  // ── Services Généraux ─────────────────────────────────────────────────────
  {
    domain: "services_generaux",
    keywords: [
      "services généraux", "services generaux", "facility",
      "agent de sécurité", "gardien", "vigile",
      "agent d'entretien", "technicien de surface",
      "coursier", "livreur",
    ],
  },

  // ── Tourisme & Loisirs ────────────────────────────────────────────────────
  {
    domain: "tourisme_loisirs",
    keywords: [
      "tourisme", "tourism", "guide touristique",
      "agent de voyage", "travel agent",
      "tour operator", "loisirs",
    ],
  },

  // ── Stage / Jeune diplômé ─────────────────────────────────────────────────
  {
    domain: "stage_jeune_diplome",
    keywords: [
      "stagiaire", "intern", "stage",
      "jeune diplômé", "jeune diplome", "fresh graduate",
      "alternant", "apprenti",
    ],
  },

  // __Etudiant ──────────────────────────────────────────────
  {
    domain: "etudiant",
    keywords: [
      "étudiant", "ETUDIANT", "student", "en recherche d'emploi",
      "recherche d'emploi", "job search",
    ],
  },

  // ── Travail Social & ONG ──────────────────────────────────────────────────
  {
    domain: "travail_social_ong",
    keywords: [
      "travail social", "travailleur social", "social worker",
      "ong", "ngo", "association",
      "humanitaire", "humanitarian",
      "développement communautaire", "community development",
      "psychologue", "psychologist", "conseiller social",
    ],
  },
];

/**
 * Classify a candidate into a sector folder.
 *
 * Priority order:
 *   1. Job's domain field (most reliable — set by recruiter)
 *   2. Keyword match on candidate.current_position
 *   3. Keyword match on candidate.ai_extracted_data.domain (raw text)
 *   4. "unknown" fallback
 *
 * @param {object} candidate  - CandidateResponse object
 * @param {object} [linkedJob] - The job object the candidate applied to
 * @returns {string} domain value from JOB_DOMAINS
 */
export function classifyCandidate(candidate, linkedJob = null) {
  // 1. Job's sector — most authoritative
  if (linkedJob?.domain) return linkedJob.domain;

  // 2. Keyword match on current position
  const position = (candidate.current_position ?? "").toLowerCase();
  if (position) {
    const match = matchKeywords(position);
    if (match) return match;
  }

  // 3. Fallback: backend-detected domain string
  const extractedDomain = candidate.ai_extracted_data?.domain;
  if (extractedDomain) {
    // If it's already a valid domain key, use it directly
    const knownKeys = CLASSIFICATION_RULES.map((r) => r.domain);
    if (knownKeys.includes(extractedDomain)) return extractedDomain;
    // Otherwise try keyword matching on it
    const match = matchKeywords(extractedDomain.toLowerCase());
    if (match) return match;
  }

  return "unknown";
}

/**
 * Run keyword rules against a text string.
 * Returns the first matching domain value, or null.
 */
function matchKeywords(text) {
  for (const rule of CLASSIFICATION_RULES) {
    for (const kw of rule.keywords) {
      if (text.includes(kw.toLowerCase())) {
        return rule.domain;
      }
    }
  }
  return null;
}