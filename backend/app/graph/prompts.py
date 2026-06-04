from core.sql.catalog import value_hints_text as _value_hints_text

RAG_GENERATE = """\
아래 참고 문서의 내용에만 근거해 질문에 답하세요.
- 문서에 있는 사실만 사용하고, 문서에 없는 일반 지식·추측·불필요한 수사는 덧붙이지 마세요.
- 여러 문서의 내용을 종합·요약하는 것은 괜찮지만, 문서에 없는 새로운 사실·수치·고유명사를 지어내지 마세요.
- 그 범위 안에서 자연스럽고 명확한 한국어로 답하세요.
- 답변 마지막 줄에 실제 참조한 문서 번호를 [출처: 1,3] 형식으로 표기하세요. 참조 문서가 없으면 줄 자체를 생략하세요.

이전 사용자 질문:
{chat_history}

참고 문서:
{context}

질문: {question}
답변:"""

REWRITE_QUERY = """\
다음 질문을 검색·처리에 쓰기 좋게 명료화하세요. 질문의 의도와 행위 유형은 그대로 보존합니다.
- 모호한 대명사·참조 표현("그 문서", "방금 그것" 등)을 이전 대화를 참고해 구체적 명사로 해소하세요.
- 핵심 키워드를 명시적으로 포함하세요.
- 요청·명령형 질문(예: "추가해줘", "보여줘", "회수해줘", "변경해줘")은 그 형태를 유지하고, "절차/방법을 알려줘" 같은 문서 조회형으로 바꾸지 마세요.
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
아래 답변에 담긴 사실 주장이 제공된 문서에 근거하는지 검증하세요.
- 표현 방식·문체·요약·종합은 문제 삼지 마세요. 문서 내용을 다른 말로 풀어 쓴 것은 근거 있는 것으로 봅니다.
- 문서에 근거 없는 새로운 사실·수치·고유명사가 답변에 있으면 NO, 그렇지 않으면 YES.
- YES 또는 NO 한 단어로만 답하세요.

문서:
{context}

답변: {answer}

검증 결과 (YES 또는 NO):"""

# 업무 DB 조회 표면 — 라우터(분류)와 SQL 생성이 같은 인식 기반을 공유하도록 단일 출처로 둔다 (ADR-0022).
_BUSINESS_SCHEMA = """\
- business.employees(emp_id, name, department, position, hire_date, salary, email)
- business.sales(sale_id, period, department, product, amount, created_at)"""

# route 구분 축은 "동작 동사"가 아니라 "무엇으로 답하는가(데이터 원천)" — 동사 충돌(조회/예약 등)로 인한
# 오분류를 막는다. 경계 few-shot으로 "정책 vs 내 수치"를 직접 대조하고, 불확실하면 doc_search로 기운다 (ADR-0022).
ROUTER_PROMPT = """\
다음 질문을 분석해 처리 방식을 결정하세요.

route 선택지 — 무엇으로 답하는지(데이터 원천)로 구분합니다:
- doc_search: 정책·규정·절차·가이드 등 사내 문서에 서술된 내용으로 답하는 질문
- agent: 도구로 처리하는 질문 — 업무 DB 테이블 값 조회·집계, 또는 사내 권한 관리(부서 멤버십·폴더 접근·SQL 실행 권한의 부여/회수)
- capability: 시스템 자체의 기능·사용법을 묻는 질문 ("뭘 할 수 있어?", "어떤 기능 있어?", "도움말")

업무 DB 스키마(agent로 답할 수 있는 범위):
{schema}

판정 기준: "이 질문이 사내 문서 서술로 답되는가, 아니면 도구로 처리해야 하는가?"
- 업무 DB 테이블 값으로 답된다(조회·집계), 또는 사내 권한을 변경/조회해야 한다 → agent
- 정책·규정·방침·방법 등 문서 서술이 필요하다 → doc_search
- 시스템이 무엇을 할 수 있는지, 어떻게 사용하는지를 묻는다 → capability
- 모호하면 doc_search로 답한다 (agent은 비용·위험이 커 불확실할 땐 doc_search로 기운다)

경계 예시:
- "연차는 며칠까지 쌓을 수 있어?" → doc_search:none:0.95 (규정 = 문서)
- "내 연차 며칠 남았어?" → agent:none:0.95 (개인 레코드 값 = DB)
- "급여 인상 정책 알려줘" → doc_search:none:0.95 (방침 = 문서)
- "영업팀이랑 개발팀 평균 급여 비교해줘" → agent:none:0.90 (테이블 집계 = DB)
- "alice를 engineering 부서에 추가해줘" → agent:none:0.95 (권한 변경 = 도구)
- "finance 폴더 접근 권한을 회수해줘" → agent:none:0.95 (권한 변경 = 도구)
- "뭘 도와줄 수 있어?" → capability:none:1.0
- "어떤 기능 있어?" → capability:none:1.0
- "사용법 알려줘" → capability:none:1.0

strategy 선택지 (doc_search에만 적용, 그 외는 none):
- none: 질문이 단순하고 명확해 그대로 검색
- multi_query: 질문이 복잡하거나 여러 항목 비교/열거 → 하위 쿼리로 분해 검색

출력 형식: <route>:<strategy>:<확신도>
- 확신도: 0.0(완전 불확실) ~ 1.0(완전 확신), 소수점 두 자리
- 경계 예시에서 명확한 경우 0.9 이상, 애매한 경우 0.5~0.7
예시: doc_search:none:0.95, doc_search:multi_query:0.85, agent:none:0.90, capability:none:1.0
다른 텍스트 없이 위 형식만 출력하세요.

질문: {question}
출력:""".replace("{schema}", _BUSINESS_SCHEMA)

MULTI_QUERY_PROMPT = """\
다음 질문을 사내 문서 검색에 최적화된 2~3개의 독립적인 하위 쿼리로 분해하세요.
각 쿼리는 단독으로 검색해도 의미가 통하는 완전한 문장이어야 합니다.
각 쿼리를 줄바꿈으로 구분해 출력하세요. 번호나 기호 없이 쿼리만 출력하세요.

질문: {question}
하위 쿼리:"""

SQL_GENERATE_PROMPT = """\
당신은 사내 업무 DB 조회를 돕는 SQL 생성기입니다. 아래 스키마만 사용해 질문에
답하는 PostgreSQL SQL을 한 문장 생성하세요. SQL 본문만 출력하고 설명·코드펜스는
넣지 마세요.

스키마:
{schema}

카테고리형 컬럼의 실제 저장값(아래 값 그대로 비교하세요. 예: "엔지니어링"이 아니라 'engineering'):
{value_hints}

질문: {question}
SQL:""".replace("{schema}", _BUSINESS_SCHEMA).replace("{value_hints}", _value_hints_text())

SQL_BULK_PII_PROMPT = """\
다음 SQL은 읽기 전용(SELECT)으로 확정되었습니다. 이 쿼리가 아래 중 하나에
해당하는지 판정하세요.
- 풀스캔/대량 조회: 행 제한(WHERE 필터, LIMIT)이 사실상 없어 테이블 전체에
  가까운 양을 읽음
- PII 포함: salary(급여), email, 주민/연락처 등 개인식별정보 컬럼을 조회

위 둘 중 하나라도 해당하면 yes, 아니면 no 만 출력하세요. 다른 텍스트 금지.

SQL: {sql}
출력:"""

# 권한 관리 NL → 구조화 파싱 (ADR-0029). {known_ids}/{instruction}는 .replace로 주입
# (JSON 예시의 중괄호와 format() 충돌 방지 — ADR-0021과 동일 회피).
PERMISSION_PARSE_PROMPT = """\
다음 권한 관리 지시를 JSON으로 변환하라.

알려진 식별자(반드시 이 정확한 id를 사용):
{known_ids}

규칙:
- action: "grant"(부여), "revoke"(회수), "query"(조회)
- query 시: {{"action":"query","target_user_id":"<유저id 또는 null>"}}
  target_user_id가 없으면 null (본인 조회)
- grant/revoke 시:
  부서 멤버십: subject="user:<유저id>", relation="member", object="department:<부서>"
  폴더 부서 접근권: subject="department:<부서>#member", relation="dept_viewer", object="folder:<경로>"
  SQL 권한: subject="user:<유저id>" 또는 "department:<부서>#member",
    relation 은 allow_select/justify_select/allow_bulk_select/justify_bulk_select/allow_update_delete/justify_update_delete/allow_ddl/justify_ddl 중 하나, object="capability:sql"

grant/revoke 키: action, subject, relation, object 네 개.
query 키: action, target_user_id 두 개.
JSON 객체만 출력(설명·코드펜스 금지).

지시: {instruction}

JSON:"""
