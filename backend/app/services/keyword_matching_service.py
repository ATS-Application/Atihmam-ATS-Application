# backend/app/services/keyword_matching_service.py
from typing import List, Dict, Any

class KeywordMatchingService:
    @staticmethod
    def calculate_match_score(candidate_skills: List[str], required_keywords: List[str]) -> Dict[str, Any]:
        """
        Calculates a match score based on keyword intersection.
        Returns the score, matched keywords, and missing keywords.
        """
        if not required_keywords:
            return {"score": 0, "matched": [], "missing": []}

        # Normalize to lowercase for reliable comparison
        candidate_set = {skill.lower().strip() for skill in candidate_skills}
        required_set = {kw.lower().strip() for kw in required_keywords}

        matched = list(required_set.intersection(candidate_set))
        missing = list(required_set.difference(candidate_set))
        
        # Calculate percentage
        score = int((len(matched) / len(required_set)) * 100)

        return {
            "score": score,
            "matched_keywords": matched,
            "missing_keywords": missing,
            "total_required": len(required_set)
        }

    @staticmethod
    def batch_score_candidates(candidates: List[Dict[str, Any]], required_keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Processes a list of candidates and attaches a match score to each.
        """
        results = []
        for candidate in candidates:
            # Assuming candidate object has a 'skills' list
            skills = candidate.get("skills", [])
            analysis = KeywordMatchingService.calculate_match_score(skills, required_keywords)
            
            candidate_with_score = {
                **candidate,
                "match_analysis": analysis,
                "final_score": analysis["score"]
            }
            results.append(candidate_with_score)
            
        return results