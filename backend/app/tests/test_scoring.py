# app/tests/test_scoring.py

from app.services.ai_service import extract_cv_info, score_candidate

def test_extract_cv_info():
    sample_cv = """
    John Doe
    Software Engineer

    Email: john@example.com
    Phone: +1 555 123 4567

    Skills:
    Python, FastAPI, React, Docker

    Experience:
    5 years building web applications.
    """

    result = extract_cv_info(sample_cv)

    assert isinstance(result, dict)
    assert "full_name" in result
    assert "skills" in result
    print(f"DEBUG: Extract result: {result}")

def test_score_candidate():
    cv_data = {
        "current_position": "Backend Developer",
        "experience_years": 4,
        "skills": ["Python", "FastAPI", "Docker"],
    }

    # This calls your scoring_service which returns a dictionary
    result = score_candidate(
        cv_data=cv_data,
        job_title="Python Backend Engineer",
        job_requirements="Python FastAPI Docker REST API cloud"
    )

    # 1. Check that it returned a dictionary
    assert isinstance(result, dict)
    # 2. Check that the 'score' key exists
    assert "score" in result
    # 3. Check that the score is a number (float or int)
    assert isinstance(result["score"], (float, int))
    # 4. Check that the score is in the valid range (0-100)
    assert 0.0 <= result["score"] <= 100.0
    print(f"DEBUG: Score result: {result}")

if __name__ == "__main__":
    print("--- Running Tests ---")
    
    print("Testing extract_cv_info...")
    test_extract_cv_info()
    print("✅ extract_cv_info passed!")
    
    print("Testing score_candidate...")
    test_score_candidate()
    print("✅ score_candidate passed!")
    
    print("--- All Tests Passed Successfully! ---")