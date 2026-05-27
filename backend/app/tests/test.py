# app/tests/test.py
from app.services.cv_classifier import classify_cv, _normalize, _score_domain, EXTENDED_DOMAINS
from app.services.cv_parser import extract_text_from_path

# 👇 Point this at a real CV that was landing in "autres"
sample_text = extract_text_from_path(r"C:\Users\LENOVO\Desktop\some_real_cv.pdf")

normalized = _normalize(sample_text)
print("=== NORMALIZED SAMPLE ===")
print(normalized[:500])
print()

scores = {}
for domain, kw_sets in EXTENDED_DOMAINS.items():
    strong = kw_sets.get("strong", [])
    weak   = kw_sets.get("weak", [])
    scores[domain] = _score_domain(normalized, strong, weak)

print("=== DOMAIN SCORES ===")
for domain, score in sorted(scores.items(), key=lambda x: -x[1]):
    print(f"  {score:6.1f}  {domain}")

print()
print("=== RESULT ===")
print("classify_cv() →", classify_cv(sample_text))