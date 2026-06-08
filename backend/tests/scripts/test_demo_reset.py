from scripts.demo_reset import (
    session_cleanup_statements,
    _SESSION_PURGE_ALL,
    _SESSION_PURGE_TODAY,
)


def test_purge_targets():
    # daesu/mido/joohwan 전체, admin은 오늘만
    assert set(_SESSION_PURGE_ALL) == {"user-daesu", "user-mido", "user-joohwan"}
    assert _SESSION_PURGE_TODAY == ["user-admin"]


def test_cleanup_statements_structure():
    stmts = session_cleanup_statements()
    assert len(stmts) == 2

    _, all_sql, all_params = stmts[0]
    assert all_params == [_SESSION_PURGE_ALL]
    assert "DELETE FROM chat_sessions" in all_sql
    # 전체 삭제는 날짜 조건이 없어야 함
    assert "AT TIME ZONE" not in all_sql

    _, today_sql, today_params = stmts[1]
    assert today_params == [_SESSION_PURGE_TODAY]
    assert "DELETE FROM chat_sessions" in today_sql
    # 오늘 기준은 KST(Asia/Seoul)로 비교
    assert "Asia/Seoul" in today_sql
