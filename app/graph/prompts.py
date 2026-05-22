RAG_GENERATE = "context:\n{context}\n\nquestion: {question}\nanswer in Korean."

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
다음 질문을 분석해 적절한 처리 방식을 선택하세요.

선택지:
- doc_search: 사내 문서에서 정보를 찾는 질문 (정책, 절차, 규정, 가이드 등)
- tool_call: 실제 작업을 수행하는 요청 (예약, 조회, 실행, 전송 등 동작)
- web_search: 외부 최신 정보가 필요한 질문 (사내 문서에 없는 일반 지식, 뉴스 등)

다음 중 하나만 출력하세요. 다른 텍스트 없이 정확히 한 단어만: doc_search, web_search, tool_call

질문: {question}
선택:"""
