import requests
import google.generativeai as genai
from app.config import get_settings

# ==========================================
# SETUP
# ==========================================

# Clear cache to ensure we pull fresh values from .env
get_settings.cache_clear()
settings = get_settings()

TEST_PROMPT = "Say hello in one short sentence."

# ==========================================
# GEMINI TEST
# ==========================================

def test_gemini():
    print("\n========== TESTING GEMINI ==========")
    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-3.5-flash")
        response = model.generate_content(TEST_PROMPT)
        print("✅ Gemini works!")
        print("Response:", response.text)
    except Exception as e:
        print("❌ Gemini failed:", e)

# ==========================================
# OPENROUTER TEST
# ==========================================

def test_openrouter():
    print("\n========== TESTING OPENROUTER ==========")
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [{"role": "user", "content": TEST_PROMPT}]
            },
            timeout=30
        )
        data = response.json()
        if response.status_code == 200:
            print("✅ OpenRouter works!")
            print("Response:", data["choices"][0]["message"]["content"])
        else:
            print(f"❌ OpenRouter failed ({response.status_code})")
            print(data)
    except Exception as e:
        print("❌ OpenRouter crashed:", e)

# ==========================================
# DEEPSEEK TEST
# ==========================================

def test_deepseek():
    print("\n========== TESTING DEEPSEEK ==========")
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": TEST_PROMPT}]
            },
            timeout=30
        )
        data = response.json()
        if response.status_code == 200:
            print("✅ DeepSeek works!")
            print("Response:", data["choices"][0]["message"]["content"])
        else:
            print(f"❌ DeepSeek failed ({response.status_code})")
            print(data)
    except Exception as e:
        print("❌ DeepSeek crashed:", e)

# =========================================
# MISTRAL TEST
# =========================================

def test_mistral():
    print("\n========== TESTING MISTRAL ==========")
    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.mistral_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistral-small-latest",
                "messages": [{"role": "user", "content": TEST_PROMPT}]
            },
            timeout=30
        )
        data = response.json()
        if response.status_code == 200:
            print("✅ Mistral works!")
            print("Response:", data["choices"][0]["message"]["content"])
        else:
            print(f"❌ Mistral failed ({response.status_code})")
            print(data)
    except Exception as e:
        print("❌ Mistral crashed:", e)

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    test_gemini()
    test_openrouter()
    test_deepseek()
    test_mistral()