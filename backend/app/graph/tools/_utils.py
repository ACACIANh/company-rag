"""공용 도구 유틸리티."""


def normalize_sql(sql: str) -> str:
    """SQL 동일성 비교용 정규화: 양끝 공백·세미콜론 제거 후 소문자 변환."""
    return sql.strip().rstrip(";").lower()


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
