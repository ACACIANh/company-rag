"""공용 도구 유틸리티."""


def strip_code_fence(text: str) -> str:
    """LLM이 감싼 ```sql ... ``` / ``` ... ``` 코드펜스를 제거한다."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        # 첫 줄(``` 또는 ```sql)과 마지막 ``` 줄 제거
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s
