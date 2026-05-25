_SECRET_KEYWORDS = ["기밀", "급여", "인사", "연봉", "평가"]
_INTERNAL_KEYWORDS = ["내부", "draft", "internal"]


def detect_sensitivity(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in _SECRET_KEYWORDS):
        return "secret"
    if any(k in lower for k in _INTERNAL_KEYWORDS):
        return "internal"
    return "public"
