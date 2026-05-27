from app.models.job import ScreeningQuestions

def safe_screening_questions(value):
    if value is None:
        return ScreeningQuestions()

    if isinstance(value, dict):
        return value

    return ScreeningQuestions()