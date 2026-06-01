RAG_GENERATE = """\
이전 대화:
{chat_history}

참고 문서:
{context}

질문: {question}
한국어로 답변하세요."""

REWRITE_QUERY = """\
다음 질문을 사내 문서 검색에 최적화되도록 재작성하세요.
모호한 대명사를 명시적 명사로 풀고, 핵심 키워드를 포함하세요.
이전 대화를 참고해 참조 표현("그 문서", "방금 그것" 등)을 구체적인 내용으로 해소하세요.
재작성된 질문만 출력하세요.

이전 대화:
{chat_history}

원본 질문: {question}
재작성된 질문:"""

GRADE_DOCUMENTS = """\
다음 문서들이 질문에 관련이 있는지 평가하고 관련성 점수를 출력하세요.
0.0(전혀 관련 없음)부터 1.0(매우 관련 있음) 사이의 숫자만 출력하세요.

질문: {question}

문서:
{context}

관련성 점수 (숫자만):"""

CHECK_HALLUCINATION = """\
다음 답변이 제공된 문서의 내용에만 근거하는지 검증하세요.
문서에 근거한 답변이면 YES, 문서에 없는 내용이 포함되어 있으면 NO로만 답하세요.

문서:
{context}

답변: {answer}

검증 결과 (YES 또는 NO):"""

ROUTER_PROMPT = """\
다음 질문을 분석해 처리 방식을 결정하세요.

route 선택지:
- doc_search: 사내 문서에서 정보를 찾는 질문 (정책, 절차, 규정, 가이드 등)
- tool_call: 실제 작업을 수행하는 요청 (예약, 조회, 실행, 전송 등 동작)

strategy 선택지 (doc_search에만 적용, 그 외는 none):
- none: 질문이 단순하고 명확해 그대로 검색
- multi_query: 질문이 복잡하거나 여러 항목 비교/열거 → 하위 쿼리로 분해 검색

출력 형식: <route>:<strategy>
예시: doc_search:none, doc_search:multi_query, tool_call:none
다른 텍스트 없이 위 형식만 출력하세요.

질문: {question}
출력:"""

MULTI_QUERY_PROMPT = """\
다음 질문을 사내 문서 검색에 최적화된 2~3개의 독립적인 하위 쿼리로 분해하세요.
각 쿼리는 단독으로 검색해도 의미가 통하는 완전한 문장이어야 합니다.
각 쿼리를 줄바꿈으로 구분해 출력하세요. 번호나 기호 없이 쿼리만 출력하세요.

질문: {question}
하위 쿼리:"""
