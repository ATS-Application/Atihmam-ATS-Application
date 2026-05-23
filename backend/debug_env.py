import os
from app.config import get_settings

print(f"Current Working Directory: {os.getcwd()}")
print(f"File exists: {os.path.exists('.env')}")

try:
    settings = get_settings()
    print(f"Gemini Key: {'LOADED' if settings.gemini_api_key else 'EMPTY'}")
    print(f"OpenRouter Key: {'LOADED' if settings.openrouter_api_key else 'EMPTY'}")
except Exception as e:
    print(f"Error loading settings: {e}")