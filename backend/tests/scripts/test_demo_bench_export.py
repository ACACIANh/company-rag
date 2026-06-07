from scripts.demo_bench import SCENES, CREDENTIALS, _build_scene_export


def test_build_scene_export_shape():
    user_map = {
        "daesu": {"display_name": "오대수", "dept": "인사"},
        "admin": {"display_name": "이우진", "dept": None},
        "mido": {"display_name": "미도", "dept": "제품"},
        "joohwan": {"display_name": "노주환", "dept": "개발"},
    }
    rows = _build_scene_export(SCENES, CREDENTIALS, user_map)

    assert len(rows) == len(SCENES)

    first = rows[0]
    assert first == {
        "id": "01",
        "account": "daesu",
        "password": "daesu123",
        "display_name": "오대수",
        "dept": "인사",
        "question": "Friday, 너는 무슨 일을 도와줄 수 있어?",
        "kind": "capability",
        "resume_text": None,
    }

    # admin은 부서 없음 → dept None
    admin_row = next(r for r in rows if r["account"] == "admin")
    assert admin_row["dept"] is None
    assert admin_row["display_name"] == "이우진"

    # JUSTIFY 장면은 resume_text 보존
    scene06 = next(r for r in rows if r["id"] == "06")
    assert scene06["resume_text"] == "감사 대비 인사 데이터 확인 목적입니다."
