import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from core.models import Answer, Chunk, SearchResult, SourceRef
from app.graph.builder import answer_question, build_graph


def _mock_chat_model(ai_messages):
    """build_graph가 chat_model.bind_tools(...)의 결과를 에이전트 모델로 쓰므로,
    bind_tools가 반환하는 객체의 .invoke가 주어진 AIMessage들을 차례로 내도록 만든다."""
    chat = MagicMock()
    bound = MagicMock()
    chat.bind_tools.return_value = bound
    bound.invoke.side_effect = list(ai_messages)
    return chat


def _mock_fga_client(roles=None, departments=None, capabilities=()):
    mock_fga = MagicMock()
    mock_fga.build_pg_filter = MagicMock(return_value=("path = $1 OR path LIKE $2", ["/company", "/company/%"]))
    mock_fga.get_readable_folders = AsyncMock(return_value=["/company"])
    mock_fga.user_roles = AsyncMock(return_value=roles or [])
    mock_fga.user_departments = AsyncMock(return_value=departments or [])
    caps = set(capabilities)

    async def check(user, relation, object_):
        return relation in caps

    mock_fga.check = check
    return mock_fga


def _mock_sql_pool(fetch_return=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [{"name": "alice", "salary": 100}])
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool


def _make_retriever(text: str = "문서", source: str = "doc.md"):
    mock = MagicMock()
    mock.retrieve = AsyncMock(return_value=[
        SearchResult(chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9)
    ])
    return mock


def _make_initial_state(question: str) -> dict:
    return {
        "question": question,
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "rewrite_strategy": None,
        "multi_queries": [],
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
        "user_id": "anonymous",
        "allowed_folders": [],
        "generated_sql": "",
        "sql_risk": "",
        "gate_decision": "",
        "justification": "",
        "agent_messages": [],
        "pending_tool_calls": [],
    }


def test_build_graph_returns_compiled_graph():
    retriever = _make_retriever()
    llm = MagicMock()
    fga_client = _mock_fga_client()
    graph = build_graph(retriever=retriever, llm=llm, fga_client=fga_client)
    assert isinstance(graph, CompiledStateGraph)


async def test_answer_question_doc_search_happy_path():
    retriever = _make_retriever(text="연차는 15일입니다.", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",
        "doc_search",
        "0.9",
        "정답",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    result = await answer_question(graph, "연차 어떻게 써?")

    assert isinstance(result, Answer)
    assert result.text == "정답"
    assert any(ref.source == "vacation.md" for ref in result.sources)


async def test_answer_question_doc_search_retry_on_low_grade():
    retriever = _make_retriever(text="내용", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "첫 재작성",
        "doc_search",
        "0.2",
        "두 번째 재작성",
        "doc_search",
        "0.8",
        "좋은 답변",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    result = await answer_question(graph, "원본 질문")

    assert result.text == "좋은 답변"


def _tool_call_msg(question="전직원 급여", tc_id="c1"):
    return AIMessage(
        content="",
        tool_calls=[{"name": "query_business_data", "args": {"question": question}, "id": tc_id}],
    )


@pytest.mark.asyncio
async def test_tool_call_allow_executes_and_answers():
    """SELECT(저위험) → 게이트 ALLOW → tool_gate가 실행 → 에이전트가 최종 답변."""
    # llm.complete: rewrite, router, sql_generate(plan), bulk/PII 판정
    llm = MagicMock()
    llm.complete.side_effect = [
        "전직원 이름 조회",                                  # rewrite
        "tool_call",                                        # router
        "SELECT name FROM business.employees",              # sql_tool.plan → SQL (AST: select)
        "no",                                               # bulk/PII 판정 → RISK_SELECT 유지 → ALLOW
    ]
    chat = _mock_chat_model([
        _tool_call_msg(),                                   # 1차: 도구 호출
        AIMessage(content="직원 이름은 alice 입니다."),       # 2차: 도구 결과 받고 최종 답변
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["sales"], capabilities=["allow_select"]),   # general → SELECT는 ALLOW
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "agent-allow-1"}}

    result = await graph.ainvoke(_make_initial_state("전직원 이름 보여줘"), config=config)
    assert "__interrupt__" not in result
    assert result["answer"] == "직원 이름은 alice 입니다."


@pytest.mark.asyncio
async def test_tool_call_justify_triggers_interrupt():
    """대량/PII SELECT → 게이트 JUSTIFY_AND_APPROVE → confirm이 HITL interrupt를 띄운다."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "전직원 급여 조회",                                  # rewrite
        "tool_call",                                        # router
        "SELECT salary FROM business.employees",            # plan → SQL
        "yes",                                              # bulk/PII → RISK_BULK_SELECT → JUSTIFY
    ]
    chat = _mock_chat_model([
        _tool_call_msg(),                                   # 도구 호출 (이후 interrupt로 멈춤)
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_bulk_select"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "agent-justify-1"}}

    result = await graph.ainvoke(_make_initial_state("전직원 급여 보여줘"), config=config)
    assert "__interrupt__" in result
    assert len(result["__interrupt__"]) > 0


@pytest.mark.asyncio
async def test_tool_call_resume_after_justify_executes_and_answers():
    """interrupt 후 Command(resume=사유) → justify_execute 실행 → 에이전트 최종 답변."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "전직원 급여 조회",                                  # rewrite
        "tool_call",                                        # router
        "SELECT salary FROM business.employees",            # plan → SQL
        "yes",                                              # bulk/PII → JUSTIFY
    ]
    chat = _mock_chat_model([
        _tool_call_msg(),                                   # 1차: 도구 호출
        AIMessage(content="급여 분포 요약 답변"),             # 2차: justify_execute 결과 받고 최종 답변
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_bulk_select"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "agent-resume-1"}}

    result = await graph.ainvoke(_make_initial_state("전직원 급여 보여줘"), config=config)
    assert "__interrupt__" in result

    final = await graph.ainvoke(Command(resume="감사 대비 급여 분포 점검"), config=config)
    assert final["answer"] == "급여 분포 요약 답변"


@pytest.mark.asyncio
async def test_tool_call_resume_empty_reason_cancels_then_answers():
    """빈 사유로 resume → justify_execute가 취소 ToolMessage → 에이전트가 취소 사실로 답변."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "전직원 급여 조회",                                  # rewrite
        "tool_call",                                        # router
        "SELECT salary FROM business.employees",            # plan → SQL
        "yes",                                              # bulk/PII → JUSTIFY
    ]
    chat = _mock_chat_model([
        _tool_call_msg(),                                   # 1차: 도구 호출
        AIMessage(content="사유 미기재로 조회가 취소되었습니다."),  # 2차: 취소 ToolMessage 받고 답변
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_bulk_select"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "agent-cancel-1"}}

    result = await graph.ainvoke(_make_initial_state("전직원 급여 보여줘"), config=config)
    assert "__interrupt__" in result

    final = await graph.ainvoke(Command(resume=""), config=config)   # 사유 미기재
    assert final["answer"] == "사유 미기재로 조회가 취소되었습니다."


@pytest.mark.asyncio
async def test_tool_call_deny_blocks_without_interrupt():
    """일반 부서원 × UPDATE → 게이트 DENY. interrupt 없이 거부 ToolMessage → 에이전트가 거부 안내."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "급여 0으로 변경",                                   # rewrite
        "tool_call",                                        # router
        "UPDATE business.employees SET salary = 0",         # plan → SQL (AST: update → DENY, bulk 판정 없음)
    ]
    chat = _mock_chat_model([
        _tool_call_msg(question="급여 0으로 변경"),           # 1차: 도구 호출
        AIMessage(content="권한이 없어 실행할 수 없습니다."),   # 2차: 거부 ToolMessage 받고 답변
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["sales"]),   # general
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "agent-deny-1"}}

    final = await graph.ainvoke(_make_initial_state("전직원 급여 0으로 바꿔"), config=config)
    assert "__interrupt__" not in final
    assert final["answer"] == "권한이 없어 실행할 수 없습니다."


@pytest.mark.asyncio
async def test_answer_question_justify_interrupt_then_resume():
    """answer_question: 1차 호출이 JUSTIFY interrupt를 노출하고, 같은 thread의
    2차 호출(사유)이 resume으로 감지되어 최종 답변을 낸다."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "전직원 급여 조회",                                  # rewrite
        "tool_call",                                        # router
        "SELECT salary FROM business.employees",            # plan → SQL
        "yes",                                              # bulk/PII → JUSTIFY
    ]
    chat = _mock_chat_model([
        _tool_call_msg(),                                   # 1차: 도구 호출 → interrupt
        AIMessage(content="급여 분포 요약 답변"),             # 2차: resume 후 최종 답변
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_bulk_select"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "api-justify-resume-1"}}

    # 1차: interrupt 노출
    first = await answer_question(graph, "전직원 급여 보여줘", config=config, user_id="bob")
    assert isinstance(first, Answer)
    assert "사유" in first.text                              # 사유 회신 안내
    assert "SELECT salary FROM business.employees" in first.text  # 계획된 SQL 노출
    assert first.sources == []

    # 2차: 같은 config → resume 감지 → 최종 답변
    second = await answer_question(graph, "감사 목적입니다", config=config, user_id="bob")
    assert second.text == "급여 분포 요약 답변"


async def test_answer_question_multi_turn_accumulates_chat_history():
    retriever = _make_retriever(text="연차는 15일", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",
        "doc_search",
        "0.9",
        "연차는 15일입니다.",
        "YES",
        "연차 상세 설명",
        "doc_search",
        "0.9",
        "더 자세히 설명하면.",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    config = {"configurable": {"thread_id": "multi-turn-test-1"}}

    result1 = await answer_question(graph, "연차 어떻게 써?", config=config)
    assert result1.text == "연차는 15일입니다."

    result2 = await answer_question(graph, "더 자세히 알려줘", config=config)
    assert result2.text == "더 자세히 설명하면."

    rewrite_prompt_turn2 = llm.complete.call_args_list[5][0][0]
    assert "연차 어떻게 써?" in rewrite_prompt_turn2


async def test_answer_question_new_session_starts_with_empty_history():
    retriever = _make_retriever(text="문서", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",
        "doc_search",
        "0.9",
        "정답",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    config = {"configurable": {"thread_id": "brand-new-session-999"}}
    result = await answer_question(graph, "연차 어떻게 써?", config=config)
    assert result.text == "정답"

    rewrite_prompt = llm.complete.call_args_list[0][0][0]
    assert "없음" in rewrite_prompt


@pytest.mark.asyncio
async def test_stream_answer_puts_tokens_and_done_in_queue():
    """stream_answer가 토큰→sources→done 순서로 큐에 넣는다."""
    from app.graph.builder import stream_answer

    mock_final = {
        "answer": "안녕하세요",
        "citations": [SourceRef(source="doc.md")],
    }
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="질문",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-1",
        is_new_session=True,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "token" in types
    assert "sources" in types
    assert types[-1] == "done"
    done_event = events[-1]
    assert done_event["session_id"] == "sess-1"

    # 토큰 이벤트를 합치면 최종 answer가 된다 (중복 없이 1회분)
    token_events = [e for e in events if e["type"] == "token"]
    assert "".join(e["content"] for e in token_events) == "안녕하세요"

    sources_event = next(e for e in events if e["type"] == "sources")
    assert sources_event["sources"] == ["doc.md"]
    # sources는 모든 token 뒤에 온다
    assert types.index("sources") > max(i for i, t in enumerate(types) if t == "token")


@pytest.mark.asyncio
async def test_stream_answer_puts_error_then_done_on_exception():
    """graph.ainvoke 예외 시 error→done 순서로 큐에 넣는다."""
    from app.graph.builder import stream_answer

    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM 오류"))

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="질문",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-1",
        is_new_session=False,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    assert events[0]["type"] == "error"
    assert "LLM 오류" in events[0]["message"]
    assert events[1]["type"] == "done"


@pytest.mark.asyncio
async def test_answer_question_uses_chat_history_fallback():
    """checkpointer가 비어있어도 chat_history_fallback이 프롬프트에 사용된다."""
    retriever = _make_retriever(text="연차는 15일", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 추가 질문",
        "doc_search",
        "0.9",
        "추가 답변",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    config = {"configurable": {"thread_id": "fallback-test-unique-1"}}

    fallback = [
        {"role": "user", "content": "연차 어떻게 써?"},
        {"role": "assistant", "content": "연차는 15일입니다."},
    ]
    result = await answer_question(
        graph, "더 자세히 알려줘", config=config, chat_history_fallback=fallback
    )
    assert result.text == "추가 답변"
    rewrite_prompt = llm.complete.call_args_list[0][0][0]
    assert "연차 어떻게 써?" in rewrite_prompt


@pytest.mark.asyncio
async def test_stream_answer_falls_back_to_session_store_history():
    """checkpointer 비어있고 기존 세션이면 session_store 메시지를 chat_history로 사용한다."""
    from app.graph.builder import stream_answer
    from core.session.base import StoredMessage

    captured: dict = {}
    mock_final = {"answer": "답변", "citations": []}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))

    async def capture_ainvoke(initial, config=None):
        captured["chat_history"] = initial.get("chat_history", [])
        return mock_final

    mock_graph.ainvoke = capture_ainvoke

    mock_store = AsyncMock()
    mock_store.get_messages = AsyncMock(return_value=[
        StoredMessage(role="user", content="이전 질문", sources=[]),
        StoredMessage(role="assistant", content="이전 답변", sources=[]),
    ])

    queue: asyncio.Queue = asyncio.Queue()
    await stream_answer(
        graph=mock_graph,
        question="후속 질문",
        config={"configurable": {"thread_id": "t-fallback"}},
        user_id="alice",
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-fallback",
        is_new_session=False,
    )

    assert captured["chat_history"] == [
        {"role": "user", "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]


@pytest.mark.asyncio
async def test_stream_answer_does_not_load_store_for_new_session():
    """새 세션이면 session_store.get_messages를 호출하지 않는다."""
    from app.graph.builder import stream_answer

    mock_final = {"answer": "답변", "citations": []}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    mock_store.get_messages = AsyncMock(return_value=[])

    queue: asyncio.Queue = asyncio.Queue()
    await stream_answer(
        graph=mock_graph,
        question="첫 질문",
        config={"configurable": {"thread_id": "t-new"}},
        user_id="alice",
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-new",
        is_new_session=True,
    )

    mock_store.get_messages.assert_not_called()


@pytest.mark.asyncio
async def test_stream_answer_saves_session():
    """완료 후 session_store에 user/assistant 메시지를 기록한다."""
    from app.graph.builder import stream_answer

    mock_final = {"answer": "답변", "citations": []}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="안녕",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-2",
        is_new_session=True,
    )

    mock_store.create_session.assert_called_once_with("sess-2", "alice", "안녕")
    assert mock_store.add_message.call_count == 2


@pytest.mark.asyncio
async def test_stream_answer_empty_answer_skips_tokens_but_sends_done():
    """빈 answer일 때 token 없이 sources/done은 정상 방출."""
    from app.graph.builder import stream_answer

    mock_final = {"answer": "", "citations": []}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="q",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        token_queue=queue,
        session_store=AsyncMock(),
        session_id="s1",
        is_new_session=False,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "token" not in types
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_stream_answer_no_duplicate_on_hallucination_retry():
    """hallucination 재생성이 일어나도 토큰은 최종 답변 1회분만 방출된다."""
    from app.graph.builder import stream_answer

    retriever = _make_retriever(text="배포는 staging 검증 후 배포한다.", source="deploy.md")
    llm = MagicMock()
    # 그래프 흐름 순서대로 llm.complete 응답:
    # rewrite_query → router → grade_documents → generate(1차) → check_hallucination(NO)
    # → generate(2차) → check_hallucination(YES)
    llm.complete.side_effect = [
        "배포 절차 재작성",       # rewrite_query
        "doc_search",            # router
        "0.9",                   # grade_documents
        "첫 번째 답변",           # generate 1차
        "NO",                    # check_hallucination 1차 → 재생성
        "최종 답변입니다",        # generate 2차
        "YES",                   # check_hallucination 2차 → 통과
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())

    queue: asyncio.Queue = asyncio.Queue()
    mock_store = AsyncMock()
    await stream_answer(
        graph=graph,
        question="배포는 어떤 절차로 진행해?",
        config={"configurable": {"thread_id": "hallu-retry-1"}},
        user_id="alice",
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-hallu",
        is_new_session=True,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    token_events = [e for e in events if e["type"] == "token"]
    joined = "".join(e["content"] for e in token_events)
    # 최종 답변만 방출, 1차 답변은 섞이지 않음 (중복 없음)
    assert joined == "최종 답변입니다"
    assert "첫 번째 답변" not in joined
    types = [e["type"] for e in events]
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_stream_answer_justify_emits_interrupt_event():
    """stream_answer: JUSTIFY interrupt → 큐에 interrupt + done 이벤트 방출. (ADR-0024)"""
    from app.graph.builder import stream_answer

    llm = MagicMock()
    llm.complete.side_effect = [
        "전직원 급여 조회",                                  # rewrite
        "tool_call",                                        # router
        "SELECT salary FROM business.employees",            # plan → SQL
        "yes",                                              # bulk/PII → JUSTIFY
    ]
    chat = _mock_chat_model([
        _tool_call_msg(),                                   # 1차: 도구 호출 → interrupt
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_bulk_select"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "stream-justify-1"}}

    mock_store = AsyncMock()
    mock_store.get_messages = AsyncMock(return_value=[])
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=graph,
        question="전직원 급여 보여줘",
        config=config,
        user_id="bob",
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-justify",
        is_new_session=False,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    # interrupt 이벤트가 방출되어야 함
    assert "interrupt" in types
    interrupt_event = next(e for e in events if e["type"] == "interrupt")
    assert "actions" in interrupt_event
    assert isinstance(interrupt_event["actions"], list)
    # done 이벤트로 마무리
    assert types[-1] == "done"
    # token/sources는 방출되지 않음 (interrupt path)
    assert "token" not in types
    assert "sources" not in types
    # session_store에 기록하지 않음 (interrupt 중 저장 안 함)
    mock_store.create_session.assert_not_called()
    mock_store.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_stream_answer_resume_after_justify():
    """stream_answer: interrupt 후 같은 config로 사유 제출 → resume 경로로 최종 답변 방출. (ADR-0024)"""
    from app.graph.builder import stream_answer

    llm = MagicMock()
    llm.complete.side_effect = [
        "전직원 급여 조회",                                  # rewrite
        "tool_call",                                        # router
        "SELECT salary FROM business.employees",            # plan → SQL
        "yes",                                              # bulk/PII → JUSTIFY
    ]
    chat = _mock_chat_model([
        _tool_call_msg(),                                   # 1차: 도구 호출 → interrupt
        AIMessage(content="급여 분포 요약 답변"),             # 2차: resume 후 최종 답변
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_bulk_select"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "stream-resume-1"}}

    mock_store = AsyncMock()
    mock_store.get_messages = AsyncMock(return_value=[])
    queue1: asyncio.Queue = asyncio.Queue()

    # 1차: interrupt 방출
    await stream_answer(
        graph=graph,
        question="전직원 급여 보여줘",
        config=config,
        user_id="bob",
        token_queue=queue1,
        session_store=mock_store,
        session_id="sess-resume",
        is_new_session=False,
    )
    events1 = []
    while not queue1.empty():
        events1.append(queue1.get_nowait())
    assert any(e["type"] == "interrupt" for e in events1)

    # 2차: 같은 config로 사유 → resume 경로 → 최종 답변
    queue2: asyncio.Queue = asyncio.Queue()
    await stream_answer(
        graph=graph,
        question="감사 목적",
        config=config,
        user_id="bob",
        token_queue=queue2,
        session_store=mock_store,
        session_id="sess-resume",
        is_new_session=False,
    )
    events2 = []
    while not queue2.empty():
        events2.append(queue2.get_nowait())

    types2 = [e["type"] for e in events2]
    assert "token" in types2
    assert "interrupt" not in types2
    token_content = "".join(e["content"] for e in events2 if e["type"] == "token")
    assert token_content == "급여 분포 요약 답변"
    assert types2[-1] == "done"
