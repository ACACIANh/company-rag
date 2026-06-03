from app.graph.tools._utils import strip_code_fence


def test_plain_text_without_fence():
    """펜스 없는 평문은 그대로 반환하되 양끝 공백은 제거."""
    text = "  SELECT * FROM users  "
    assert strip_code_fence(text) == "SELECT * FROM users"


def test_language_tagged_fence():
    """```sql ... ``` 형태의 언어 태그 펜스를 제거하고 내용만 반환."""
    text = "```sql\nSELECT 1\n```"
    assert strip_code_fence(text) == "SELECT 1"


def test_bare_fence():
    """``` ... ``` 형태의 언어 태그 없는 펜스를 제거하고 내용만 반환."""
    text = "```\n{\"a\": 1}\n```"
    assert strip_code_fence(text) == '{"a": 1}'


def test_fence_with_leading_trailing_whitespace():
    """펜스 전체를 감싼 공백을 제거한 후 처리."""
    text = "  ```json\n  [1, 2, 3]  \n  ```  "
    assert strip_code_fence(text) == "[1, 2, 3]"


def test_multiline_content_in_fence():
    """펜스 내 여러 줄의 내용을 모두 유지."""
    text = "```sql\nSELECT *\nFROM users\nWHERE age > 18\n```"
    expected = "SELECT *\nFROM users\nWHERE age > 18"
    assert strip_code_fence(text) == expected


def test_empty_fence():
    """펜스가 비어 있으면 빈 문자열 반환."""
    text = "```\n\n```"
    assert strip_code_fence(text) == ""


def test_fence_with_inner_whitespace_lines():
    """펜스 내 공백 줄들은 유지."""
    text = "```\nline1\n\nline3\n```"
    expected = "line1\n\nline3"
    assert strip_code_fence(text) == expected


def test_incomplete_fence_no_closing():
    """닫는 펜스가 없으면 펜스로 간주하지 않음 (첫 줄만 제거)."""
    text = "```sql\nSELECT 1"
    # 첫 줄이 ```로 시작하므로 제거되고, 마지막 줄이 ``` 아니므로 유지
    assert strip_code_fence(text) == "SELECT 1"


def test_incomplete_fence_no_opening():
    """여는 펜스가 없으면 펜스로 간주하지 않음."""
    text = "SELECT 1\n```"
    assert strip_code_fence(text) == "SELECT 1\n```"
