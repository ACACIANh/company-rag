# TechCorp 시드 전면 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수동 테스트용 시드를 7부서·사원 12명·문서 ~46개의 "TechCorp" 세계관으로 전면 재구성한다(ADR-0014).

**Architecture:** 데이터는 코드와 분리(`config/*.yaml` + `docs/company/**`). FGA 모델·pre-filter·eval 러너는 불변. 기존 alice/bob/carol/admin 매핑을 보존해 API 테스트 churn을 0으로 만들고, 신규 8명·5부서·31문서는 additive로 쌓는다. 권한 매트릭스는 단위테스트로, 검색 품질은 eval로 검증한다.

**Tech Stack:** YAML(config), Markdown(corpus), pytest, OpenFGA(`scripts/seed_fga.py`), pgvector(`scripts/build_index.py`).

**작업 디렉토리:** 모든 명령은 `backend/` cwd 기준. 인터프리터는 `.venv/bin/python`.

**선행 사실 (탐색으로 확정):**
- 실제 `config/*.yaml`을 로드하는 테스트 0건. `test_seed_fga.py`(인라인 데이터)·`test_permission_node.py`(mock)·`test_rag_with_fga.py`(합성 폴더 주입) 모두 데이터 변경에 강건.
- API 테스트만 런타임에 `config/users.yaml` 로드(`app/api/auth.py`). 단정: alice→user-alice/`["engineering"]`, admin→c_level/부서없음. **보존 매핑으로 생존.** `test_admin_users_returns_list`는 `isinstance(list)`만 검사(개수 무관) → 생존.
- 기존 문서엔 front matter 없음. source = 폴더 상대경로 파일명. path = base_path(`/company`) + 폴더. 회사명은 기존 문서가 "acmecorp" 사용 — 신규 문서도 동일 톤 유지(테스트 비단정, cosmetic).
- eval 러너는 권한 무관. `run(question)` 콜백에 recall@k·mrr·kw 채점. committed baseline 파일 없음 → aggregate 수치를 ADR에 수기 기록.

---

## Task 1: folders.yaml 재작성 + 신규 private 폴더 튜플 검증

**Files:**
- Modify: `config/folders.yaml`
- Test: `tests/scripts/test_seed_fga.py`

- [ ] **Step 1: 신규 private 폴더 튜플 회귀 테스트 추가**

`tests/scripts/test_seed_fga.py` 맨 끝에 추가:

```python
# ── TechCorp 재구성: 신규 private 부서 폴더 ──────────────────
def test_finance_private_and_dept_viewer():
    folders = {"/company/finance": {"private": True, "dept_viewers": ["finance"]}}
    tuples = _build_tuples([], folders)
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/finance")
    assert _find(
        tuples, user="department:finance#member", relation="dept_viewer",
        object="folder:/company/finance",
    )


def test_legal_private_and_dept_viewer():
    folders = {"/company/legal": {"private": True, "dept_viewers": ["legal"]}}
    tuples = _build_tuples([], folders)
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/legal")
    assert _find(
        tuples, user="department:legal#member", relation="dept_viewer",
        object="folder:/company/legal",
    )
```

- [ ] **Step 2: 테스트 실패 확인 (아직은 통과 — `_build_tuples`는 데이터 무관 순수함수)**

Run: `.venv/bin/python -m pytest tests/scripts/test_seed_fga.py -q`
Expected: PASS (이 테스트들은 인라인 데이터라 즉시 통과 — folders.yaml 작성과 독립. 회귀 안전망 역할).

- [ ] **Step 3: folders.yaml 전면 교체**

`config/folders.yaml` 전체를 아래로 교체:

```yaml
# 폴더 권한. 튜플 생성의 단일 소스. base_path=/company 가 prefix로 붙은 path 기준.
# 정책: 전체공개가 기본 — /company 에 public 을 부여하면 하위 폴더는 상속(표식 없는 폴더 = 공개).
#       private: true 폴더만 공개를 차단하고 dept_viewers 로 명시 부서에만 권한 부여.
#       c_level 역할은 super_reader 로 전사 열람(private 도 관통, 하위 상속).
folders:
  /company:
    public: true               # 전 직원 공개 (하위 상속)
    super_readers: [c_level]    # 전사 상위 열람권 (private 관통, 하위 상속)
  /company/common:
    # 상속 — 전사공통 공개 문서
  /company/engineering:
    # 상속 — 엔지니어링 공개 문서
  /company/engineering/ops:
    private: true              # 배포·인시던트 운영 문서 — 공개 차단
    dept_viewers: [engineering]
  /company/product:
    # 상속 — 프로덕트 공개 문서
  /company/design:
    # 상속 — 디자인 공개 문서
  /company/sales:
    # 상속 — 세일즈 공개 문서
  /company/hr:
    private: true              # 인사 문서 — 공개 차단
    dept_viewers: [hr]
  /company/finance:
    private: true              # 재무 문서 — 공개 차단
    dept_viewers: [finance]
  /company/legal:
    private: true              # 법무 문서 — 공개 차단
    dept_viewers: [legal]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/scripts/test_seed_fga.py -q`
Expected: PASS (전체).

- [ ] **Step 5: Commit**

```bash
git add config/folders.yaml tests/scripts/test_seed_fga.py
git commit -m "feat(seed): folders.yaml 7부서 트리로 확장 (product/design/sales/finance/legal)"
```

---

## Task 2: users.yaml 재작성 (12명) + API 테스트 회귀 확인

**Files:**
- Modify: `config/users.yaml`
- Test: `tests/app/api/test_auth.py`, `tests/app/api/test_admin.py` (단정 변경 없음 — 회귀만)

- [ ] **Step 1: users.yaml 전면 교체**

`config/users.yaml` 전체를 아래로 교체 (alice/bob/carol/admin 매핑·비번·id 보존):

```yaml
users:
  # admin: /admin 엔드포인트(재색인 등) 운영용. FGA 권한은 c_level 역할 → super_reader 전사 열람.
  - username: admin
    password: admin123
    user_id: user-admin
    roles: [admin, user]
    fga_roles: [c_level]
  # alice: 엔지니어링. 공개 + /company/engineering/ops(private) 열람.
  - username: alice
    password: alice123
    user_id: user-alice
    roles: [user]
    departments: [engineering]
  # bob: 인사. 공개 + /company/hr(private) 열람.
  - username: bob
    password: bob123
    user_id: user-bob
    roles: [user]
    departments: [hr]
  # carol: 무소속. 전체공개(public)만, private 차단.
  - username: carol
    password: carol123
    user_id: user-carol
    roles: [user]
    departments: []
  # dave: 프로덕트(public).
  - username: dave
    password: dave123
    user_id: user-dave
    roles: [user]
    departments: [product]
  # erin: 디자인(public).
  - username: erin
    password: erin123
    user_id: user-erin
    roles: [user]
    departments: [design]
  # frank: 세일즈(public).
  - username: frank
    password: frank123
    user_id: user-frank
    roles: [user]
    departments: [sales]
  # grace: 재무. 공개 + /company/finance(private).
  - username: grace
    password: grace123
    user_id: user-grace
    roles: [user]
    departments: [finance]
  # heidi: 법무. 공개 + /company/legal(private).
  - username: heidi
    password: heidi123
    user_id: user-heidi
    roles: [user]
    departments: [legal]
  # ivan: 교차부서 — 엔지니어링+프로덕트. 공개 + eng/ops(private).
  - username: ivan
    password: ivan123
    user_id: user-ivan
    roles: [user]
    departments: [engineering, product]
  # judy: 교차부서 — 세일즈+재무. 공개 + finance(private).
  - username: judy
    password: judy123
    user_id: user-judy
    roles: [user]
    departments: [sales, finance]
  # karl: 교차부서 — 인사+법무. 공개 + hr + legal(두 private).
  - username: karl
    password: karl123
    user_id: user-karl
    roles: [user]
    departments: [hr, legal]
```

- [ ] **Step 2: API 인증 회귀 테스트 통과 확인 (보존 매핑 검증)**

Run: `.venv/bin/python -m pytest tests/app/api/test_auth.py tests/app/api/test_admin.py -q`
Expected: PASS (alice→`["engineering"]`, admin→c_level 단정 보존으로 무변경 통과).

- [ ] **Step 3: Commit**

```bash
git add config/users.yaml
git commit -m "feat(seed): users.yaml 12명으로 확장 (교차부서·무소속·c_level 매트릭스)"
```

---

## Task 3: 신규 문서 31개 작성 + team-structure.md 갱신

**Files (Create — 31개):**
- `docs/company/common/code-of-conduct.md`
- `docs/company/engineering/architecture-overview.md`, `tech-stack.md`, `oncall-rotation.md`
- `docs/company/engineering/ops/monitoring-runbook.md`
- `docs/company/product/{product-roadmap,prd-template,release-process,feature-flags,user-research}.md`
- `docs/company/design/{design-system,brand-guidelines,ux-principles,accessibility}.md`
- `docs/company/sales/{sales-playbook,pricing,crm-process,contract-template,quota-policy}.md`
- `docs/company/hr/{hiring-process,compensation-bands,leave-of-absence,disciplinary-policy}.md`
- `docs/company/finance/{budget-process,expense-approval,procurement,financial-reporting}.md`
- `docs/company/legal/{nda-policy,data-privacy,contract-review,ip-policy}.md`
- Modify: `docs/company/common/team-structure.md`

**작성 규칙:** front matter 없음. 기존 문서 톤·분량(실내용, 요약 스텁 아님, 한국어, `##` 섹션 구조). 회사명은 기존 문서와 동일하게 "acmecorp"/"acme" 유지. **아래 "고정 사실"은 Task 4 eval 문항이 의존하므로 정확히 반영.**

**고정 사실 (eval 의존 — 정확히 작성):**
- `sales/contract-template.md`: "계약서"·"표준 계약 조항"·"갱신" 포함. NDA·MSA 언급.
- `legal/contract-review.md`: "계약 검토"·"법무 승인"·"리뷰" 포함. 계약 검토 SLA "영업일 3일".
- `legal/data-privacy.md`: "개인정보"·"보안"·"GDPR"·"파기" 포함.
- `finance/budget-process.md`: "예산"·"분기"·"편성" 포함. 부서 예산 신청 마감 "분기 시작 2주 전".
- `finance/expense-approval.md`: "비용"·"승인"·"한도" 포함. 50만원 초과 시 부서장 승인.
- `sales/pricing.md`: "가격"·"플랜"·"할인" 포함. 연간 결제 시 "20% 할인".
- `sales/quota-policy.md`: "쿼터"·"목표"·"커미션" 포함.
- `product/release-process.md`: "릴리스"·"배포"·"체크리스트" 포함.
- `product/feature-flags.md`: "피처 플래그"·"롤아웃"·"점진" 포함.
- `design/design-system.md`: "디자인 시스템"·"컴포넌트"·"토큰" 포함.
- `hr/hiring-process.md`: "채용"·"면접"·"단계" 포함. 면접 "3단계".
- `hr/compensation-bands.md`: "연봉"·"밴드"·"레벨" 포함.
- `engineering/oncall-rotation.md`: "온콜"·"로테이션"·"교대" 포함. 온콜 주기 "1주".
- `engineering/ops/monitoring-runbook.md`: "모니터링"·"알람"·"대시보드" 포함.

**team-structure.md 갱신:** 7부서(engineering·product·design·sales·hr·finance·legal)·사원 12명 구성을 반영. 기존 "AI/ML팀 인원" 등 옛 내용은 신 조직으로 교체. eval 의존 사실: "부서"·"7개"·"엔지니어링" 포함.

- [ ] **Step 1: common·engineering·engineering/ops 문서 작성 (5개)**

`code-of-conduct.md`, `architecture-overview.md`, `tech-stack.md`, `oncall-rotation.md`, `monitoring-runbook.md`를 위 규칙대로 작성.

- [ ] **Step 2: product·design 문서 작성 (9개)**

product 5개 + design 4개를 작성.

- [ ] **Step 3: sales·hr 문서 작성 (10개)**

sales 5개 + hr 4개(신규)를 작성.

- [ ] **Step 4: finance·legal 문서 작성 (8개)**

finance 4개 + legal 4개를 작성.

- [ ] **Step 5: team-structure.md 갱신**

신 조직(7부서·12명) 반영해 교체.

- [ ] **Step 6: 문서 수·폴더 배치 확인**

Run: `find docs/company -name '*.md' | wc -l && find docs/company -type d | sort`
Expected: `46`, 그리고 디렉토리: company/common·engineering·engineering/ops·product·design·sales·hr·finance·legal.

- [ ] **Step 7: Commit**

```bash
git add docs/company
git commit -m "feat(seed): TechCorp 코퍼스 31개 신규 문서 + team-structure 갱신"
```

---

## Task 4: eval/questions.yaml 재작성

**Files:**
- Modify: `tests/eval/questions.yaml`

- [ ] **Step 1: questions.yaml 전면 교체**

`tests/eval/questions.yaml` 전체를 아래로 교체. doc_search 24 + tool_call 6 = 30문항. expected_source는 파일명만(기존 컨벤션). 검색 함정 4종 포함.

```yaml
questions:
  # ── common (전사공통, 기존 재사용 문서) ──────────────────────
  - question: "연차는 며칠이야?"
    expected_keywords: ["연차", "일"]
    expected_source: "vacation-policy.md"
    expected_route: "doc_search"
  - question: "입사 2년 차 직원 연차 일수가 몇 일이야?"
    expected_keywords: ["연차", "15일"]
    expected_source: "vacation-policy.md"
    expected_route: "doc_search"
  - question: "온보딩 절차가 어떻게 돼?"
    expected_keywords: ["온보딩", "입사"]
    expected_source: "onboarding.md"
    expected_route: "doc_search"
  - question: "기기 분실했을 때 어떻게 해야 해?"
    expected_keywords: ["분실", "IT팀"]
    expected_source: "security-policy.md"
    expected_route: "doc_search"
  - question: "재택근무 정책이 어떻게 돼?"
    expected_keywords: ["재택", "근무"]
    expected_source: "remote-work-policy.md"
    expected_route: "doc_search"
  - question: "복지 혜택에 뭐가 있어?"
    expected_keywords: ["복지", "혜택"]
    expected_source: "benefits.md"
    expected_route: "doc_search"
  # ── team-structure (갱신 문서) ──────────────────────────────
  - question: "회사 부서 구조가 어떻게 돼?"
    expected_keywords: ["부서", "팀"]
    expected_source: "team-structure.md"
    expected_route: "doc_search"
  # ── engineering ────────────────────────────────────────────
  - question: "코드 리뷰할 때 주의사항이 뭐야?"
    expected_keywords: ["리뷰", "PR"]
    expected_source: "code-review-guide.md"
    expected_route: "doc_search"
  - question: "온콜 로테이션 주기가 어떻게 돼?"
    expected_keywords: ["온콜", "1주"]
    expected_source: "oncall-rotation.md"
    expected_route: "doc_search"
  - question: "우리 기술 스택이 뭐야?"
    expected_keywords: ["기술", "스택"]
    expected_source: "tech-stack.md"
    expected_route: "doc_search"
  # ── engineering/ops (private) ──────────────────────────────
  - question: "배포 절차가 어떻게 돼?"
    expected_keywords: ["배포", "절차"]
    expected_source: "deployment-guide.md"
    expected_route: "doc_search"
  - question: "모니터링 알람은 어디서 봐?"
    expected_keywords: ["모니터링", "알람"]
    expected_source: "monitoring-runbook.md"
    expected_route: "doc_search"
  # ── product ────────────────────────────────────────────────
  - question: "릴리스 체크리스트가 뭐야?"
    expected_keywords: ["릴리스", "체크리스트"]
    expected_source: "release-process.md"
    expected_route: "doc_search"
  - question: "피처 플래그 어떻게 써?"
    expected_keywords: ["피처 플래그", "롤아웃"]
    expected_source: "feature-flags.md"
    expected_route: "doc_search"
  # ── design ─────────────────────────────────────────────────
  - question: "디자인 시스템 컴포넌트 어디 있어?"
    expected_keywords: ["디자인 시스템", "컴포넌트"]
    expected_source: "design-system.md"
    expected_route: "doc_search"
  # ── sales ──────────────────────────────────────────────────
  - question: "연간 결제하면 할인 얼마야?"
    expected_keywords: ["할인", "20%"]
    expected_source: "pricing.md"
    expected_route: "doc_search"
  - question: "영업 쿼터랑 커미션 어떻게 정해져?"
    expected_keywords: ["쿼터", "커미션"]
    expected_source: "quota-policy.md"
    expected_route: "doc_search"
  # ── hr ─────────────────────────────────────────────────────
  - question: "채용 면접은 몇 단계야?"
    expected_keywords: ["면접", "3단계"]
    expected_source: "hiring-process.md"
    expected_route: "doc_search"
  - question: "성과 평가는 어떻게 진행돼?"
    expected_keywords: ["성과", "평가"]
    expected_source: "performance-review.md"
    expected_route: "doc_search"
  # ── finance ────────────────────────────────────────────────
  - question: "부서 예산 신청 마감이 언제야?"
    expected_keywords: ["예산", "2주"]
    expected_source: "budget-process.md"
    expected_route: "doc_search"
  # ── 검색 함정: 동음이의 + 권한 분산 ─────────────────────────
  - question: "계약 검토는 법무에서 며칠 걸려?"   # legal/contract-review vs sales/contract-template
    expected_keywords: ["계약", "검토"]
    expected_source: "contract-review.md"
    expected_route: "doc_search"
  - question: "표준 계약서 양식 어디 있어?"          # sales/contract-template vs legal/contract-review
    expected_keywords: ["계약서", "양식"]
    expected_source: "contract-template.md"
    expected_route: "doc_search"
  - question: "50만원 넘는 비용 쓰려면 누구 승인 받아?"  # finance/expense-approval vs common/expense-policy
    expected_keywords: ["비용", "승인"]
    expected_source: "expense-approval.md"
    expected_route: "doc_search"
  - question: "개인정보 파기 규정이 뭐야?"            # legal/data-privacy vs common/security-policy
    expected_keywords: ["개인정보", "파기"]
    expected_source: "data-privacy.md"
    expected_route: "doc_search"
  # ── tool_call (코퍼스 독립 — 기존 유지) ─────────────────────
  - question: "다음 주 월요일 회의실 A 예약해줘"
    expected_keywords: ["회의실", "예약"]
    expected_route: "tool_call"
  - question: "팀 전체에 슬랙으로 공지 보내줘"
    expected_keywords: ["슬랙", "공지"]
    expected_route: "tool_call"
  - question: "내 연차 잔여일 인사 시스템에서 조회해줘"
    expected_keywords: ["연차", "잔여"]
    expected_route: "tool_call"
  - question: "김철수 대리에게 메일 보내줘"
    expected_keywords: ["메일"]
    expected_route: "tool_call"
  - question: "오늘 오후 2시 캘린더에 미팅 잡아줘"
    expected_keywords: ["캘린더", "미팅"]
    expected_route: "tool_call"
  - question: "내 Jira 미완료 티켓 목록 보여줘"
    expected_keywords: ["Jira", "티켓"]
    expected_route: "tool_call"
```

- [ ] **Step 2: yaml 파싱·문항 수 확인**

Run: `.venv/bin/python -c "import yaml; q=yaml.safe_load(open('tests/eval/questions.yaml'))['questions']; print(len(q), sum(1 for x in q if x['expected_route']=='doc_search'), sum(1 for x in q if x['expected_route']=='tool_call'))"`
Expected: `30 24 6`

- [ ] **Step 3: Commit**

```bash
git add tests/eval/questions.yaml
git commit -m "test(eval): 신 코퍼스 기준 questions.yaml 재작성 (24 doc_search + 검색함정 4 + 6 tool_call)"
```

---

## Task 5: 권한 매트릭스 단위테스트 추가 (교차부서·무소속·super_reader)

**Files:**
- Modify: `tests/app/test_rag_with_fga.py`

기존 파일의 `_fga_with_folders`/`_mock_retriever`/`_run` 헬퍼를 재사용해 신 트리의 교차부서·무소속·super_reader 경계를 추가 검증한다.

- [ ] **Step 1: 권한 매트릭스 테스트 추가**

`tests/app/test_rag_with_fga.py` 맨 끝에 추가:

```python
# ── TechCorp 재구성: 교차부서·무소속·super_reader 매트릭스 ──────────────
async def test_cross_dept_user_sees_both_private_folders():
    # karl(hr+legal): 두 private 폴더 모두 가시, finance(타 private)는 차단.
    fga = _fga_with_folders(
        ["/company", "/company/common", "/company/sales", "/company/hr", "/company/legal"]
    )
    retriever = _mock_retriever([
        {"text": "인사", "source": "hr/perf.md", "path": "/company/hr"},
        {"text": "법무", "source": "legal/nda.md", "path": "/company/legal"},
        {"text": "재무", "source": "finance/budget.md", "path": "/company/finance"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever))["documents"]]
    assert "hr/perf.md" in sources
    assert "legal/nda.md" in sources
    assert "finance/budget.md" not in sources  # 타 부서 private 차단


async def test_cross_dept_public_plus_one_private():
    # judy(sales+finance): public(sales) + finance(private) 가시, hr(타 private) 차단.
    fga = _fga_with_folders(
        ["/company", "/company/common", "/company/sales", "/company/finance"]
    )
    retriever = _mock_retriever([
        {"text": "영업", "source": "sales/pricing.md", "path": "/company/sales"},
        {"text": "재무", "source": "finance/budget.md", "path": "/company/finance"},
        {"text": "인사", "source": "hr/perf.md", "path": "/company/hr"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever))["documents"]]
    assert "sales/pricing.md" in sources
    assert "finance/budget.md" in sources
    assert "hr/perf.md" not in sources


async def test_super_reader_sees_all_private():
    # admin(c_level): 모든 private 관통. ListObjects가 전 폴더를 반환.
    all_folders = [
        "/company", "/company/common", "/company/engineering", "/company/engineering/ops",
        "/company/product", "/company/design", "/company/sales",
        "/company/hr", "/company/finance", "/company/legal",
    ]
    fga = _fga_with_folders(all_folders)
    retriever = _mock_retriever([
        {"text": "인사", "source": "hr/perf.md", "path": "/company/hr"},
        {"text": "재무", "source": "finance/budget.md", "path": "/company/finance"},
        {"text": "법무", "source": "legal/nda.md", "path": "/company/legal"},
        {"text": "운영", "source": "engineering/ops/deploy.md", "path": "/company/engineering/ops"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever, "전사 조회"))["documents"]]
    assert set(sources) == {
        "hr/perf.md", "finance/budget.md", "legal/nda.md", "engineering/ops/deploy.md"
    }


async def test_public_only_user_blocked_from_all_new_privates():
    # carol(무소속): 신규 private(finance·legal)도 prefix 누수 없이 차단 — ADR-0015 회귀.
    fga = _fga_with_folders(["/company", "/company/common", "/company/sales"])
    retriever = _mock_retriever([
        {"text": "영업", "source": "sales/pricing.md", "path": "/company/sales"},
        {"text": "재무", "source": "finance/budget.md", "path": "/company/finance"},
        {"text": "법무", "source": "legal/nda.md", "path": "/company/legal"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever))["documents"]]
    assert sources == ["sales/pricing.md"]  # 신규 private 차단
```

- [ ] **Step 2: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/test_rag_with_fga.py -q`
Expected: PASS (기존 4 + 신규 4 = 8).

- [ ] **Step 3: Commit**

```bash
git add tests/app/test_rag_with_fga.py
git commit -m "test(fga): 교차부서·무소속·super_reader 권한 매트릭스 케이스 추가"
```

---

## Task 6: 전체 단위테스트 + 재시드/재색인 + eval 재기록

**Files:** (검증만 — 코드 변경 없음)

- [ ] **Step 1: 전체 단위테스트 통과 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (기존 318+ 에 신규 케이스 가산. 실패 0). 실패 시 해당 Task로 돌아가 수정.

- [ ] **Step 2: 재시드 + 재색인 (로컬 OpenFGA·DB 필요)**

> 인프라(OpenFGA·Postgres)가 떠 있어야 한다. `docker-compose` 기동 후 실행. 인프라 미가용 환경이면 이 Step은 인프라 준비 후 수행하고, 실행 사실을 기록한다.

Run:
```bash
.venv/bin/python -m scripts.seed_fga
.venv/bin/python -m scripts.build_index
```
Expected: seed_fga가 12명·9폴더 튜플 등록, build_index가 46개 문서 인덱싱(문서 수 출력 확인).

- [ ] **Step 3: eval 실행 + aggregate 기록**

Run: `.venv/bin/python -m scripts.eval_rag_basic` (이 스크립트가 `run_eval`을 호출).
Expected: `Aggregate: recall@1=.. recall@3=.. recall@5=.. mrr=.. kw=.. errors=0/30`. 이 수치를 기록.

> 주의: 검색 함정(동음이의 4문항) 때문에 mrr이 기존 대비 내려갈 수 있다. 이는 "권한·동음이의 함정 추가에 따른 의도된 변화"다(DoD 규칙2). errors>0이면 expected_source 파일명 오타·미생성 문서 의심 → Task 3/4 점검.

- [ ] **Step 4: (커밋 없음 — 산출물은 다음 Task의 ADR 기록)**

---

## Task 7: ADR-0014 Status 갱신 + 인덱스 재생성 + 마무리

**Files:**
- Modify: `docs/superpowers/decisions/ADR-0014-manual-test-seed-rebuild.md`
- Regenerate: `docs/superpowers/decisions/README.md`

- [ ] **Step 1: ADR-0014 Status·내용 갱신**

`ADR-0014` 상단 Status 줄을 교체:

```markdown
> **Status**: 🟢 적용완료 — TechCorp 7부서/12명/46문서 재구성 (spec: 2026-06-02-techcorp-seed-rebuild-design.md)
```

그리고 문서 하단 `## Status` 섹션 아래에 실측 baseline을 추가:

```markdown
## 구현 결과 (2026-06-02)

- 규모: 부서 7 + 전사공통, 사원 12(교차 3·무소속 1·c_level 1), 문서 46.
- eval baseline(신 코퍼스): recall@1=<측정값> recall@3=<측정값> recall@5=<측정값> mrr=<측정값> kw=<측정값> (errors=0/30).
  - 검색 함정(동음이의 4문항) 도입에 따른 의도된 mrr 변화. 권한 매트릭스는 `test_rag_with_fga.py` 단위테스트로 검증.
- 영향 자산: config/{users,folders}.yaml, docs/company/**, tests/eval/questions.yaml, tests/app/test_rag_with_fga.py.
```

> `<측정값>`은 Task 6 Step 3에서 기록한 실제 aggregate 수치로 채운다.

- [ ] **Step 2: ADR 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `docs/superpowers/decisions/README.md` 재생성, ADR-0014 행이 🟢 적용완료로 표시.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/decisions/ADR-0014-manual-test-seed-rebuild.md docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0014 적용완료 — TechCorp 시드 재구성 + eval baseline 기록"
```

- [ ] **Step 4: 마무리 — finishing-a-development-branch 스킬로 PR/머지 결정**

`feat/techcorp-seed-rebuild` 브랜치 작업 완료. `superpowers:finishing-a-development-branch` 스킬을 호출해 PR(DoD 체크리스트 포함) 또는 머지를 결정한다. 머지 후 ADR-0014는 별도 phase 태그 대상 아님(데이터 작업).

---

## Self-Review (작성자 점검 완료)

- **Spec 커버리지:** 섹션1(folders.yaml)=Task1 · 섹션2(users 12명)=Task2 · 섹션3(문서46+함정)=Task3+4 · 섹션4(eval/fixture)=Task4+5+6 · 산출물순서8단계=Task1~7 매핑. 누락 없음.
- **플레이스홀더:** `<측정값>`은 의도된 런타임 산출(Task6에서 측정 후 Task7에서 기입) — 명시적 지시 있음. 그 외 TBD/TODO 없음.
- **타입 일관성:** `_build_tuples(users, folders)`·`_fga_with_folders`·`_mock_retriever`·`_run` 시그니처는 기존 파일에서 확인한 실제 헬퍼와 일치. yaml 키(public/private/dept_viewers/super_readers/departments/fga_roles)는 seed_fga가 읽는 키와 일치.
- **검색 함정 ↔ 고정 사실 정합:** Task4 eval 문항의 expected_source·keyword가 Task3 "고정 사실"과 1:1 대응(contract-review/template, expense-approval, data-privacy, pricing 20%, hiring 3단계, oncall 1주, budget 2주).
