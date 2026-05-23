# app/services/scoring_service.py

import re
from difflib import SequenceMatcher


COMMON_STOPWORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "with",
    "for",
    "to",
    "of",
    "in",
    "on",
    "at",
    "is",
    "are",
    "required",
    "experience",
    "knowledge",
    "skill",
    "skills",
}


def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.lower()

    text = re.sub(r"[^a-zA-Z0-9+#.\s]", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_keywords(text: str) -> list[str]:
    text = normalize_text(text)

    words = text.split()

    keywords = []

    for word in words:
        if len(word) < 2:
            continue

        if word in COMMON_STOPWORDS:
            continue

        if word not in keywords:
            keywords.append(word)

    return keywords


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def keyword_match_score(
    candidate_skills: list[str],
    job_keywords: list[str],
):
    matched = []
    missing = []

    if not job_keywords:
        return 0, matched, missing

    normalized_skills = [
        normalize_text(skill)
        for skill in candidate_skills
    ]

    for keyword in job_keywords:
        found = False

        for skill in normalized_skills:
            if (
                keyword in skill
                or skill in keyword
                or similarity(keyword, skill) > 0.80
            ):
                found = True
                break

        if found:
            matched.append(keyword)
        else:
            missing.append(keyword)

    score = (
        len(matched) / len(job_keywords)
    ) * 100

    return round(score, 1), matched, missing


def experience_score(
    years: int | None,
) -> float:
    if years is None:
        return 40

    if years >= 10:
        return 100

    if years >= 7:
        return 90

    if years >= 5:
        return 80

    if years >= 3:
        return 70

    if years >= 1:
        return 60

    return 40


def compute_candidate_score(
    cv_data: dict,
    job_title: str,
    job_requirements: str,
):
    """
    Returns ATS score on 100.
    """

    candidate_skills = cv_data.get(
        "skills",
        [],
    )

    experience_years = cv_data.get(
        "experience_years",
        0,
    )

    combined_job_text = f"""
    {job_title}
    {job_requirements}
    """

    job_keywords = extract_keywords(
        combined_job_text
    )

    keyword_score, matched, missing = (
        keyword_match_score(
            candidate_skills,
            job_keywords,
        )
    )

    exp_score = experience_score(
        experience_years
    )

    # FINAL SCORE
    final_score = (
        keyword_score * 0.8
        + exp_score * 0.2
    )

    final_score = round(final_score, 1)

    reasoning = (
        f"Matched {len(matched)} "
        f"keywords out of "
        f"{len(job_keywords)}."
    )

    return {
        "score": final_score,
        "matched_keywords": matched[:20],
        "missing_keywords": missing[:20],
        "reasoning": reasoning,
    }