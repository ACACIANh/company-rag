import pytest
from shared.fga.sensitivity import detect_sensitivity


@pytest.mark.parametrize("text,expected", [
    ("2024년 연봉 협상 결과", "secret"),
    ("인사 평가 Q3 결과", "secret"),
    ("기밀 프로젝트 계획서", "secret"),
    ("급여 명세서 2024", "secret"),
    ("내부 공지 — draft 버전", "internal"),
    ("INTERNAL USE ONLY", "internal"),
    ("신제품 발표 자료", "public"),
    ("회사 소개 페이지", "public"),
    ("", "public"),
])
def test_detect_sensitivity(text, expected):
    assert detect_sensitivity(text) == expected
