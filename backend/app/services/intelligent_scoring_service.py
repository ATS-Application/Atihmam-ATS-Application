# backend/app/services/intelligent_scoring_service.py
"""
Système de scoring intelligent et adaptatif pour l'ATS.
VERSION AMÉLIORÉE :
  - Déduplication de projets par chevauchement de dates
  - Mesure de profondeur de compétence étendue
  - Score d'expérience réelle (non additif)
  - Apprentissage adaptatif du recruteur
  - Recommandations enrichies avec explication narrative

Changelog (feedback loop fix):
  - compute_intelligent_score now accepts a `weights` dict overriding the
    6 score_breakdown weights (skill_match, experience, project_complexity,
    seniority, domain_diversity, career_progression). Falls back to
    INTELLIGENT_SCORE_DEFAULT_WEIGHTS (scoring_service) when None/incomplete.
    This is the weight vector that feedback.py reads/writes via
    app_config.ats_weights, closing the recruiter-feedback loop.
"""

import re
import json
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from collections import defaultdict

from app.services.scoring_service import INTELLIGENT_SCORE_DEFAULT_WEIGHTS


# ============================================================
# CONSTANTES & CONFIGURATION
# ============================================================

SENIORITY_KEYWORDS = {
    "lead": 1.4, "senior": 1.3, "sr.": 1.3, "principal": 1.5,
    "staff": 1.4, "architect": 1.5, "director": 1.6, "head of": 1.6,
    "manager": 1.3, "tech lead": 1.4, "junior": 0.7, "jr.": 0.7,
    "intern": 0.5, "stagiaire": 0.5, "débutant": 0.6,
}

COMPLEXITY_INDICATORS = [
    "microservices", "kubernetes", "k8s", "distributed", "scalable",
    "architecture", "million users", "high availability", "real-time",
    "machine learning", "deep learning", "llm", "production", "ci/cd",
    "millions", "terraform", "iac", "event-driven", "cqrs", "ddd",
    "zero downtime", "99.9%", "sla", "load balancer", "sharding",
]

TECH_FAMILIES = {
    "python": ["django", "fastapi", "flask", "sqlalchemy", "celery", "pandas", "numpy", "pytorch", "tensorflow"],
    "javascript": ["react", "vue", "angular", "node.js", "nodejs", "next.js", "express", "typescript"],
    "java": ["spring", "spring boot", "hibernate", "maven", "gradle", "quarkus"],
    "devops": ["docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions", "gitlab ci", "aws", "gcp", "azure"],
    "data": ["spark", "hadoop", "kafka", "airflow", "dbt", "databricks", "snowflake", "elasticsearch"],
    "databases": ["postgresql", "mysql", "mongodb", "redis", "cassandra", "dynamodb", "neo4j"],
}

CERTIFICATION_BONUS = {
    "aws certified": 8, "google cloud certified": 8, "azure certified": 7,
    "kubernetes certified": 9, "cka": 9, "ckad": 8, "terraform associate": 7,
    "scrum master": 5, "pmp": 6, "csm": 5, "togaf": 6,
}

COMMON_STOPWORDS = {
    "and", "or", "the", "a", "an", "with", "for", "to", "of", "in",
    "on", "at", "is", "are", "required", "experience", "knowledge",
    "skill", "skills", "using", "tools", "strong", "good", "excellent",
    "familiar", "proficient", "ability", "work", "team", "develop",
}


# ============================================================
# UTILITAIRES TEXTE
# ============================================================

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-zA-Z0-9+#.\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def extract_keywords(text: str) -> list[str]:
    text = normalize_text(text)
    words = text.split()
    return [w for w in words if len(w) >= 2 and w not in COMMON_STOPWORDS]


# ============================================================
# DÉDUPLICATION DE PROJETS
# ============================================================

def _parse_year_range(text: str) -> tuple[int | None, int | None]:
    """
    Extrait une plage d'années depuis un texte de projet.
    Ex: "2020 - 2022" → (2020, 2022), "Jan 2021 - Present" → (2021, current_year)
    """
    current_year = datetime.now().year
    match = re.search(r'(20\d{2})\s*[-–]\s*(20\d{2}|present|aujourd|now|actuel)', text, re.IGNORECASE)
    if match:
        start = int(match.group(1))
        end_raw = match.group(2).lower()
        end = current_year if any(w in end_raw for w in ["present", "aujourd", "now", "actuel"]) else int(match.group(2))
        return start, end
    single = re.search(r'(20\d{2})', text)
    if single:
        y = int(single.group(1))
        return y, y
    return None, None


def _projects_overlap(p1_text: str, p2_text: str, threshold: float = 0.65) -> bool:
    """
    Détermine si deux projets se chevauchent (texte similaire OU dates qui se croisent).
    """
    norm1 = normalize_text(p1_text)
    norm2 = normalize_text(p2_text)
    if similarity(norm1, norm2) >= threshold:
        return True
    start1, end1 = _parse_year_range(p1_text)
    start2, end2 = _parse_year_range(p2_text)
    if all(v is not None for v in [start1, end1, start2, end2]):
        dates_overlap = not (end1 < start2 or end2 < start1)  # type: ignore[operator]
        if dates_overlap:
            tech_overlap = len(set(norm1.split()) & set(norm2.split())) / max(len(set(norm1.split())), 1)
            if tech_overlap >= 0.4:
                return True
    return False


def deduplicate_projects(project_texts: list[str]) -> dict:
    """
    Analyse une liste de descriptions de projets et retourne :
    - unique_projects : liste des projets sans doublons
    - duplicates_removed : nombre de doublons détectés
    - real_duration_years : durée réelle estimée (sans comptage double)
    - diversity_ratio : ratio diversité (0 à 1)
    """
    if not project_texts:
        return {
            "unique_projects": [],
            "duplicates_removed": 0,
            "real_duration_years": 0,
            "diversity_ratio": 1.0,
        }

    unique: list[str] = []
    duplicates_removed = 0

    for project in project_texts:
        is_duplicate = any(_projects_overlap(project, u) for u in unique)
        if is_duplicate:
            duplicates_removed += 1
        else:
            unique.append(project)

    intervals: list[tuple[int, int]] = []
    for p in unique:
        start, end = _parse_year_range(p)
        if start is not None and end is not None:
            intervals.append((start, end))  # type: ignore[arg-type]

    real_duration = _union_duration(intervals)

    total = len(project_texts)
    diversity_ratio = len(unique) / total if total > 0 else 1.0

    return {
        "unique_projects": unique,
        "duplicates_removed": duplicates_removed,
        "real_duration_years": real_duration,
        "diversity_ratio": round(diversity_ratio, 2),
    }


def _union_duration(intervals: list[tuple[int, int]]) -> float:
    """
    Calcule la durée totale réelle en fusionnant les intervalles qui se chevauchent.
    Ex: [(2019,2021), (2020,2022)] → 3 ans (pas 4).
    """
    if not intervals:
        return 0.0
    sorted_ivs = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[int, int]] = [sorted_ivs[0]]
    for start, end in sorted_ivs[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return sum(end - start for start, end in merged)


# ============================================================
# ANALYSE DE SENIORITÉ
# ============================================================

def detect_seniority_multiplier(cv_text: str, current_position: str | None) -> float:
    """Détecte le niveau de seniorité depuis le texte du CV."""
    combined = normalize_text(f"{cv_text or ''} {current_position or ''}")
    multiplier = 1.0
    for keyword, mult in SENIORITY_KEYWORDS.items():
        if keyword in combined:
            multiplier = max(multiplier, mult)
    return multiplier


# ============================================================
# ANALYSE DE COMPLEXITÉ DES PROJETS
# ============================================================

def analyze_project_complexity(cv_text: str) -> float:
    """
    Analyse la complexité des projets mentionnés dans le CV.
    Retourne un score entre 0 et 100.
    """
    if not cv_text:
        return 30.0

    text = normalize_text(cv_text)
    hits = sum(1 for indicator in COMPLEXITY_INDICATORS if indicator in text)

    large_numbers = re.findall(r'\b(\d+)\s*(million|billion|k users|m users)', text)
    hits += len(large_numbers) * 2

    complexity = min(100.0, hits * 10)
    return max(20.0, complexity)


# ============================================================
# DÉTECTION DE DIVERSITÉ (AMÉLIORÉE)
# ============================================================

def detect_project_diversity(cv_text: str, skills: list[str]) -> dict:
    """
    Analyse la diversité des projets.
    Version améliorée : tient compte de la déduplication de projets.
    """
    if not cv_text or not skills:
        return {"diversity_score": 70.0, "penalty": 0.0, "unique_domains": []}

    text = normalize_text(cv_text)
    found_families = []
    for family, techs in TECH_FAMILIES.items():
        if any(tech in text for tech in techs) or family in text:
            found_families.append(family)

    unique_domains = len(found_families)
    diversity_score = min(100.0, unique_domains * 15 + 10)

    if len(skills) > 5 and unique_domains <= 1:
        penalty = 15.0
    elif unique_domains <= 2 and len(skills) > 8:
        penalty = 8.0
    else:
        penalty = 0.0

    diversity_bonus = 5.0 if unique_domains >= 5 else 0.0

    return {
        "diversity_score": min(100.0, diversity_score + diversity_bonus),
        "penalty": penalty,
        "unique_domains": found_families,
        "domain_count": unique_domains,
    }


# ============================================================
# ANALYSE DES CERTIFICATIONS
# ============================================================

def analyze_certifications(cv_text: str) -> float:
    """Détecte et score les certifications."""
    if not cv_text:
        return 0.0

    text = normalize_text(cv_text)
    total_bonus = 0.0
    found = []
    for cert, bonus in CERTIFICATION_BONUS.items():
        if cert in text:
            total_bonus += bonus
            found.append(cert)

    return min(30.0, total_bonus)


# ============================================================
# SCORING DES COMPÉTENCES AVEC PROFONDEUR (AMÉLIORÉ)
# ============================================================

def deep_skill_match_score(
    candidate_skills: list[str],
    job_keywords: list[str],
    cv_text: str = "",
    experience_years: int | None = None,
) -> dict:
    """
    Scoring avancé des compétences:
    - Correspondance exacte/floue
    - Profondeur (technologies associées dans la même famille)
    - Contexte d'utilisation réel dans le CV (pas juste listé)
    - Bonus d'écosystème : si plusieurs techs d'une même famille sont présentes
    """
    if not job_keywords:
        return {"score": 0.0, "matched": [], "missing": [], "depth_bonus": 0.0, "ecosystem_bonus": 0.0}

    normalized_skills = [normalize_text(s) for s in candidate_skills]
    cv_text_normalized = normalize_text(cv_text)

    matched = []
    missing = []
    depth_bonus = 0.0
    ecosystem_bonus = 0.0

    for keyword in job_keywords:
        found = False

        for skill in normalized_skills:
            if (keyword in skill or skill in keyword or
                    similarity(keyword, skill) > 0.82):
                found = True
                break

        if not found and keyword in cv_text_normalized:
            found = True
            context_pattern = r'.{0,50}' + re.escape(keyword) + r'.{0,50}'
            context_matches = re.findall(context_pattern, cv_text_normalized)
            if len(context_matches) >= 2:
                depth_bonus += 2.0

        if found:
            matched.append(keyword)
            for family, techs in TECH_FAMILIES.items():
                if keyword in techs or keyword == family:
                    family_hits = sum(1 for t in techs if t in cv_text_normalized)
                    if family_hits >= 4:
                        depth_bonus += 8.0
                        ecosystem_bonus += 3.0
                    elif family_hits >= 3:
                        depth_bonus += 5.0
                        ecosystem_bonus += 2.0
                    elif family_hits >= 2:
                        depth_bonus += 2.0
        else:
            missing.append(keyword)

    base_score = (len(matched) / len(job_keywords)) * 100
    return {
        "score": round(base_score, 1),
        "matched": matched[:25],
        "missing": missing[:25],
        "depth_bonus": min(20.0, round(depth_bonus, 1)),
        "ecosystem_bonus": min(10.0, round(ecosystem_bonus, 1)),
    }


# ============================================================
# SCORING D'EXPÉRIENCE RÉELLE (NON-LINÉAIRE + ANTI-GONFLEMENT)
# ============================================================

def experience_score_nonlinear(
    years: int | None,
    project_dedup_result: dict | None = None,
) -> dict:
    """
    Score d'expérience non-linéaire.
    Si un résultat de déduplication est fourni, on utilise la durée réelle
    (sans comptage double de projets simultanés).

    Retourne un dict avec score et real_years utilisés.
    """
    effective_years = years
    dedup_note = ""
    if project_dedup_result and project_dedup_result.get("real_duration_years", 0) > 0:
        real_dur = project_dedup_result["real_duration_years"]
        duplicates = project_dedup_result.get("duplicates_removed", 0)
        if duplicates > 0 and years and real_dur < years:
            effective_years = real_dur
            dedup_note = f"Adjusted from {years}y declared to {real_dur}y real (removed {duplicates} overlapping projects)"

    if effective_years is None:
        return {"score": 35.0, "effective_years": None, "note": "Not specified"}

    if effective_years <= 0:
        score = 20.0
    elif effective_years == 1:
        score = 45.0
    elif effective_years == 2:
        score = 55.0
    elif effective_years == 3:
        score = 65.0
    elif effective_years == 4:
        score = 72.0
    elif effective_years == 5:
        score = 78.0
    elif effective_years <= 7:
        score = 83.0
    elif effective_years <= 10:
        score = 90.0
    elif effective_years <= 15:
        score = 95.0
    else:
        score = 100.0

    return {
        "score": score,
        "effective_years": effective_years,
        "note": dedup_note or f"{effective_years} years",
    }


# ============================================================
# PROGRESSION DE CARRIÈRE
# ============================================================

def analyze_career_progression(cv_text: str, experience_years: int | None) -> float:
    """
    Analyse la progression de carrière.
    Détecte si le candidat a progressé (junior → senior, etc.)
    """
    if not cv_text:
        return 50.0

    text = normalize_text(cv_text)

    progression_signals = [
        "promoted", "promotion", "promu", "progression",
        "led team", "managed team", "grew from", "evolved",
        "increased responsibility", "team lead", "tech lead",
    ]

    progression_hits = sum(1 for signal in progression_signals if signal in text)

    if experience_years and experience_years >= 5 and progression_hits == 0:
        return 55.0
    elif progression_hits >= 3:
        return 90.0
    elif progression_hits >= 1:
        return 75.0
    else:
        return 60.0


# ============================================================
# APPRENTISSAGE DES PRÉFÉRENCES DU RECRUTEUR (AMÉLIORÉ)
# ============================================================

def load_recruiter_preferences(supabase_client: Any) -> dict:
    """
    Charge les préférences du recruteur depuis la base de données.
    Analyse les candidats précédemment recrutés (status='hired').
    Version améliorée : ajoute des suggestions intelligentes basées sur les tendances.
    """
    try:
        hired = (
            supabase_client.table("candidates")
            .select("skills, experience_years, ai_extracted_data, score, current_position")
            .eq("status", "hired")
            .not_.is_("skills", "null")
            .execute()
        )

        if not hired.data:
            return {
                "preferred_skills": {},
                "avg_experience": None,
                "common_domains": [],
                "hired_count": 0,
                "suggestions": [],
            }

        skill_frequency: dict[str, int] = defaultdict(int)
        experience_values = []
        domain_frequency: dict[str, int] = defaultdict(int)
        position_texts = []

        for candidate in hired.data:
            for skill in (candidate.get("skills") or []):
                skill_frequency[normalize_text(skill)] += 1

            if candidate.get("experience_years"):
                experience_values.append(candidate["experience_years"])

            ai_data = candidate.get("ai_extracted_data") or {}
            tech_text = normalize_text(json.dumps(ai_data))
            for family, techs in TECH_FAMILIES.items():
                if any(t in tech_text for t in techs) or family in tech_text:
                    domain_frequency[family] += 1

            if candidate.get("current_position"):
                position_texts.append(normalize_text(candidate["current_position"]))

        avg_exp = (sum(experience_values) / len(experience_values)
                   if experience_values else None)

        top_skills = dict(sorted(skill_frequency.items(), key=lambda x: x[1], reverse=True)[:20])
        top_domains = sorted(domain_frequency.items(), key=lambda x: x[1], reverse=True)[:5]

        suggestions = _generate_recruiter_suggestions(
            top_skills=top_skills,
            top_domains=[d[0] for d in top_domains],
            avg_exp=avg_exp,
            hired_count=len(hired.data),
        )

        return {
            "preferred_skills": top_skills,
            "avg_experience": avg_exp,
            "common_domains": [d[0] for d in top_domains],
            "hired_count": len(hired.data),
            "suggestions": suggestions,
        }
    except Exception as e:
        print(f"[PREFERENCES] Could not load recruiter preferences: {e}")
        return {
            "preferred_skills": {},
            "avg_experience": None,
            "common_domains": [],
            "hired_count": 0,
            "suggestions": [],
        }


def _generate_recruiter_suggestions(
    top_skills: dict[str, int],
    top_domains: list[str],
    avg_exp: float | None,
    hired_count: int,
) -> list[str]:
    """
    Génère des suggestions intelligentes basées sur les patterns de recrutement.
    Ex: "Tu recrutes souvent des profils Docker + Cloud →  ajouter Kubernetes améliore le matching."
    """
    suggestions = []

    if hired_count < 2:
        return ["Hire more candidates to unlock intelligent suggestions."]

    skill_pairs = {
        ("docker", "kubernetes"): "You hire Docker profiles often — adding Kubernetes requirement would refine matches.",
        ("python", "fastapi"): "Python is your top skill — FastAPI candidates tend to match your profile.",
        ("react", "typescript"): "React appears often in your hires — TypeScript is frequently paired with it.",
        ("aws", "terraform"): "Cloud-focused hires detected — Terraform expertise improves infrastructure fit.",
        ("machine learning", "python"): "ML + Python is a strong pattern in your hires — consider PyTorch/TensorFlow depth.",
    }

    skill_keys = set(top_skills.keys())
    for (s1, s2), suggestion in skill_pairs.items():
        if s1 in skill_keys and s2 not in skill_keys:
            suggestions.append(suggestion)

    if avg_exp is not None:
        if avg_exp < 3:
            suggestions.append(f"You tend to hire junior profiles (~{avg_exp:.1f}y avg). Consider filtering by growth potential.")
        elif avg_exp >= 6:
            suggestions.append(f"You consistently hire senior talent (~{avg_exp:.1f}y avg). Seniority score weight is higher for you.")

    if "devops" in top_domains and "data" not in top_domains:
        suggestions.append("DevOps-heavy pipeline detected — data engineering skills are rarely seen in your hires.")
    if len(top_domains) <= 2:
        suggestions.append("Your hiring is concentrated in few domains — consider broadening to improve team diversity.")

    return suggestions[:5]


def apply_recruiter_preference_bonus(
    candidate_skills: list[str],
    experience_years: int | None,
    preferences: dict,
) -> float:
    """
    Calcule un bonus basé sur les préférences apprises du recruteur.
    """
    if not preferences.get("preferred_skills"):
        return 0.0

    bonus = 0.0
    preferred = preferences["preferred_skills"]
    normalized_skills = [normalize_text(s) for s in candidate_skills]

    for skill in normalized_skills:
        if skill in preferred:
            freq = preferred[skill]
            bonus += min(5.0, freq * 1.5)

    avg_exp = preferences.get("avg_experience")
    if avg_exp and experience_years:
        diff = abs(experience_years - avg_exp)
        if diff <= 1:
            bonus += 5.0
        elif diff <= 2:
            bonus += 2.5

    return min(20.0, round(bonus, 1))


# ============================================================
# SCORE FINAL INTELLIGENT (AMÉLIORÉ)
# ============================================================

def compute_intelligent_score(
    cv_data: dict,
    job_title: str,
    job_requirements: str,
    cv_raw_text: str = "",
    recruiter_preferences: dict | None = None,
    project_texts: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> dict:
    """
    Calcule un score ATS intelligent multi-dimensionnel.

    Nouvelles dimensions v2:
    - Déduplication de projets (évite 3 projets × 2 ans = 6 ans ❌)
    - Expérience réelle après déduplication
    - Bonus d'écosystème (plusieurs techs d'une même famille)
    - Suggestions intelligentes du recruteur

    Pondération (par défaut, voir INTELLIGENT_SCORE_DEFAULT_WEIGHTS):
    1. Matching compétences (avec profondeur) — 35%
    2. Expérience réelle (non-linéaire + anti-doublon) — 20%
    3. Complexité des projets — 15%
    4. Séniorité — 10%
    5. Diversité des domaines — 10%
    6. Progression de carrière — 10%
    + Bonus additifs: depth, ecosystem, certifications, recruiter fit
    - Pénalités: répétition de projets, faible diversité

    `weights`, si fourni, surcharge les 6 poids ci-dessus (clés: skill_match,
    experience, project_complexity, seniority, domain_diversity,
    career_progression). Toute clé absente ou non reconnue retombe sur
    INTELLIGENT_SCORE_DEFAULT_WEIGHTS. C'est le mécanisme par lequel le
    feedback recruteur (feedback.py → app_config.ats_weights) influence
    le scoring des candidats.
    """
    w = dict(INTELLIGENT_SCORE_DEFAULT_WEIGHTS)
    if weights:
        for key in w:
            if key in weights:
                try:
                    w[key] = float(weights[key])
                except (TypeError, ValueError):
                    pass  # keep default for this dimension

    candidate_skills = cv_data.get("skills") or []
    experience_years = cv_data.get("experience_years")
    current_position = cv_data.get("current_position") or ""

    combined_job_text = f"{job_title} {job_requirements}"
    job_keywords = extract_keywords(combined_job_text)

    # ── Déduplication de projets ──────────────────
    dedup_result = None
    repetition_penalty = 0.0
    if project_texts:
        dedup_result = deduplicate_projects(project_texts)
        if dedup_result["duplicates_removed"] > 0:
            repetition_ratio = 1.0 - dedup_result["diversity_ratio"]
            repetition_penalty = round(min(15.0, repetition_ratio * 25), 1)

    # ── 1. Matching compétences ──────────────────────────────
    skill_result = deep_skill_match_score(
        candidate_skills, job_keywords, cv_raw_text, experience_years
    )
    skill_score = skill_result["score"]
    depth_bonus = skill_result["depth_bonus"]
    ecosystem_bonus = skill_result["ecosystem_bonus"]

    # ── 2. Expérience réelle (anti-gonflement) ───────────────
    exp_result = experience_score_nonlinear(experience_years, dedup_result)
    exp_score = exp_result["score"]

    # ── 3. Complexité des projets ────────────────────────────
    complexity_score = analyze_project_complexity(cv_raw_text)

    # ── 4. Séniorité ─────────────────────────────────────────
    seniority_mult = detect_seniority_multiplier(cv_raw_text, current_position)
    seniority_score = min(100.0, (seniority_mult - 0.5) / 1.1 * 100)

    # ── 5. Diversité des domaines ─────────────────────────────
    diversity_result = detect_project_diversity(cv_raw_text, candidate_skills)
    diversity_score = diversity_result["diversity_score"]
    diversity_penalty = diversity_result["penalty"]

    # ── 6. Certifications ─────────────────────────────────────
    cert_bonus = analyze_certifications(cv_raw_text)

    # ── 7. Progression de carrière ────────────────────────────
    career_score = analyze_career_progression(cv_raw_text, experience_years)

    # ── 8. Préférences du recruteur ───────────────────────────
    recruiter_bonus = 0.0
    if recruiter_preferences:
        recruiter_bonus = apply_recruiter_preference_bonus(
            candidate_skills, experience_years, recruiter_preferences
        )

    # ── Score final pondéré ───────────────────────────────────
    raw_score = (
        skill_score * w["skill_match"]
        + exp_score * w["experience"]
        + complexity_score * w["project_complexity"]
        + seniority_score * w["seniority"]
        + diversity_score * w["domain_diversity"]
        + career_score * w["career_progression"]
    )

    raw_score += depth_bonus + ecosystem_bonus + cert_bonus + recruiter_bonus
    raw_score -= diversity_penalty + repetition_penalty

    final_score = round(min(100.0, max(0.0, raw_score)), 1)

    # ── Génération du raisonnement ────────────────────────────
    reasoning_parts = []
    if skill_result["matched"]:
        reasoning_parts.append(
            f"Matched {len(skill_result['matched'])}/{len(job_keywords)} keywords"
        )
    if depth_bonus > 0:
        reasoning_parts.append(f"+{depth_bonus:.0f}pts depth bonus")
    if ecosystem_bonus > 0:
        reasoning_parts.append(f"+{ecosystem_bonus:.0f}pts ecosystem mastery")
    if cert_bonus > 0:
        reasoning_parts.append(f"+{cert_bonus:.0f}pts certifications")
    if recruiter_bonus > 0:
        reasoning_parts.append(f"+{recruiter_bonus:.0f}pts recruiter fit")
    if diversity_penalty > 0:
        reasoning_parts.append(f"-{diversity_penalty:.0f}pts low diversity")
    if repetition_penalty > 0:
        reasoning_parts.append(
            f"-{repetition_penalty:.0f}pts project repetition "
            f"({dedup_result['duplicates_removed']} overlapping projects removed)"
        )
    if exp_result.get("note") and "Adjusted" in (exp_result.get("note") or ""):
        reasoning_parts.append(exp_result["note"])
    if seniority_mult != 1.0:
        level = "senior" if seniority_mult > 1.0 else "junior"
        reasoning_parts.append(f"Level: {level} ({seniority_mult:.1f}x)")

    reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Standard match."

    return {
        "score": final_score,
        "matched_keywords": skill_result["matched"],
        "missing_keywords": skill_result["missing"],
        "reasoning": reasoning,
        "score_breakdown": {
            "skill_match": round(skill_score, 1),
            "experience": round(exp_score, 1),
            "project_complexity": round(complexity_score, 1),
            "seniority": round(seniority_score, 1),
            "domain_diversity": round(diversity_score, 1),
            "career_progression": round(career_score, 1),
            "depth_bonus": round(depth_bonus, 1),
            "ecosystem_bonus": round(ecosystem_bonus, 1),
            "certification_bonus": round(cert_bonus, 1),
            "recruiter_fit_bonus": round(recruiter_bonus, 1),
            "diversity_penalty": round(diversity_penalty, 1),
            "repetition_penalty": round(repetition_penalty, 1),
        },
        # Weights actually applied to the 6 primary dimensions above
        # (defaults, or learned weights from app_config.ats_weights).
        "weights_used": w,
        "insights": {
            "seniority_level": _get_seniority_label(seniority_mult),
            "unique_domains": diversity_result["unique_domains"],
            "complexity_level": _get_complexity_label(complexity_score),
            "experience_note": exp_result.get("note", ""),
            "effective_years": exp_result.get("effective_years"),
            "project_dedup": {
                "duplicates_removed": dedup_result["duplicates_removed"] if dedup_result else 0,
                "real_duration_years": dedup_result["real_duration_years"] if dedup_result else None,
                "diversity_ratio": dedup_result["diversity_ratio"] if dedup_result else 1.0,
            } if dedup_result else None,
        },
        "recruiter_suggestions": (recruiter_preferences or {}).get("suggestions", []),
    }


def _get_seniority_label(mult: float) -> str:
    if mult >= 1.5:
        return "Principal/Architect"
    elif mult >= 1.3:
        return "Senior"
    elif mult >= 1.1:
        return "Mid-level"
    elif mult >= 0.8:
        return "Junior"
    else:
        return "Intern/Entry"


def _get_complexity_label(score: float) -> str:
    if score >= 80:
        return "High complexity"
    elif score >= 50:
        return "Medium complexity"
    else:
        return "Standard complexity"


# ============================================================
# RECOMMANDATIONS INTELLIGENTES (AMÉLIORÉES)
# ============================================================

def generate_smart_recommendations(
    candidates: list[dict],
    recruiter_preferences: dict,
) -> list[dict]:
    """
    Génère des recommandations intelligentes avec :
    - Similarité avec les candidats recrutés
    - Explication narrative détaillée
    - Catégorisation (skills, expérience, domaine)
    """
    if not candidates or not recruiter_preferences.get("preferred_skills"):
        return []

    recommendations = []
    preferred_skills = set(recruiter_preferences["preferred_skills"].keys())
    avg_exp = recruiter_preferences.get("avg_experience")
    common_domains = set(recruiter_preferences.get("common_domains", []))

    for candidate in candidates[:50]:
        candidate_skills = {normalize_text(s) for s in (candidate.get("skills") or [])}
        overlap = candidate_skills & preferred_skills
        overlap_ratio = len(overlap) / max(len(preferred_skills), 1)

        if overlap_ratio < 0.3:
            continue

        match_reasons = []
        match_categories = []

        if overlap:
            match_reasons.append(f"Shares {len(overlap)} skills with your hired profiles")
            match_categories.append("skills")

        exp = candidate.get("experience_years")
        if avg_exp and exp:
            exp_diff = abs(exp - avg_exp)
            if exp_diff <= 1.5:
                match_reasons.append(f"Experience ({exp}y) close to your avg hire ({avg_exp:.1f}y)")
                match_categories.append("experience")

        cv_text = normalize_text(json.dumps(candidate.get("ai_extracted_data") or {}))
        for domain in common_domains:
            if domain in cv_text or any(t in cv_text for t in TECH_FAMILIES.get(domain, [])):
                match_reasons.append(f"Fits your '{domain}' domain pattern")
                match_categories.append("domain")
                break

        confidence = round(min(100.0, overlap_ratio * 100 + len(match_reasons) * 5), 1)

        recommendations.append({
            "candidate_id": candidate["id"],
            "candidate_name": candidate.get("full_name", "Unknown"),
            "match_reason": " · ".join(match_reasons) if match_reasons else f"Shares {len(overlap)} skills",
            "match_categories": list(set(match_categories)),
            "overlap_skills": list(overlap)[:5],
            "confidence": confidence,
            "current_score": candidate.get("score"),
        })

    return sorted(recommendations, key=lambda x: x["confidence"], reverse=True)[:10]
