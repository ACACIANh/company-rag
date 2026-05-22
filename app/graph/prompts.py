RAG_GENERATE = "context:\n{context}\n\nquestion: {question}\nanswer in Korean."

REWRITE_QUERY = """\
다음 질문을 사내 문서 검색에 최적화되도록 재작성하세요.
모호한 대명사를 명시적 명사로 풀고, 핵심 키워드를 포함하세요.
재작성된 질문만 출력하세요.

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
