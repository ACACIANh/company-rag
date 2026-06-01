# 사내 문서 RAG 챗봇 — 접근 권한 제어 작업 지시서

> **스택:** Python · OpenFGA · Chroma · LangChain
> **모델:** ABAC + RBAC 혼합 (OpenFGA Zanzibar 기반)

---

## 1. OpenFGA 환경 구성

```bash
docker run -p 8080:8080 openfga/openfga run
pip install openfga-sdk chromadb langchain
```

Authorization Model 등록 (`model.fga`)

```
model
  schema 1.1

type user

type team
  relations
    define member : [user]
    define admin  : [user]

type document
  relations
    define owner   : [user]
    define editor  : [user, team#member]
    define viewer  : [user, team#member, editor]
    define can_edit : editor or owner
    define can_view : viewer or can_edit
```

---

## 2. 문서 메타데이터 스키마

Chroma 청크 저장 시 아래 필드 필수 포함

```python
metadata = {
    # OpenFGA 연동 (필수)
    "document_id": "doc:기획서_2024",   # OpenFGA object ID와 1:1
    "team_id":     "team:marketing",
    "sensitivity": "internal",          # public | internal | secret

    # 검색·출처용
    "title":       "2024 마케팅 기획서",
    "source_path": "/docs/plan.pdf",
    "page":        3,
}
```

---

## 3. 문서 등록 파이프라인

```python
def register_document(file_path, team_id, owner_id):
    doc_id      = generate_doc_id(file_path)
    sensitivity = detect_sensitivity(file_path)   # 아래 참고
    chunks      = split_document(file_path)

    # 1) Chroma 임베딩 저장
    collection.add(
        ids=[f"{doc_id}_chunk_{i}" for i in range(len(chunks))],
        documents=chunks,
        metadatas=[{"document_id": doc_id, "team_id": team_id,
                    "sensitivity": sensitivity} for _ in chunks],
    )

    # 2) OpenFGA 권한 등록
    openfga_client.write(body=WriteRequest(writes=build_tuples(
        doc_id, owner_id, team_id, sensitivity
    )))


def build_tuples(doc_id, owner_id, team_id, sensitivity):
    tuples = [{"user": f"user:{owner_id}", "relation": "owner",
               "object": f"document:{doc_id}"}]
    if sensitivity == "public":
        tuples.append({"user": "user:*",              "relation": "viewer", "object": f"document:{doc_id}"})
    elif sensitivity == "internal":
        tuples.append({"user": f"team:{team_id}#member", "relation": "viewer", "object": f"document:{doc_id}"})
    # secret → 개별 지정만 허용
    return tuples


def detect_sensitivity(file_path) -> str:
    text = extract_text(file_path).lower()
    if any(k in text for k in ["기밀", "급여", "인사", "연봉"]):
        return "secret"
    if any(k in text for k in ["내부", "draft", "internal"]):
        return "internal"
    return "public"
```

---

## 4. RAG 검색 파이프라인 (Pre-filter)

```python
def rag_query(user_id, question) -> str:
    # 1) 접근 가능한 문서 ID 조회
    res = openfga_client.list_objects(body=ListObjectsRequest(
        user=f"user:{user_id}", relation="can_view", type="document"
    ))
    allowed_ids = [o.split(":")[1] for o in res.objects]

    if not allowed_ids:
        return "접근 가능한 문서가 없습니다."

    # 2) Chroma Pre-filter 검색
    results = collection.query(
        query_texts=[question],
        n_results=5,
        where={"document_id": {"$in": allowed_ids}},
    )

    # 3) LLM 전달
    context = "\n".join(results["documents"][0])
    return llm_chain.run(context=context, question=question)
```

---

## 5. 마이그레이션 (기존 문서)

**순서:** 최근 6개월 → 민감 문서 → 나머지 구문서

```python
def migrate_batch(docs, batch_size=50):
    failed = []
    for i in range(0, len(docs), batch_size):
        for doc in docs[i:i+batch_size]:
            try:
                register_document(doc.path, doc.team_id, doc.owner_id)
            except Exception as e:
                failed.append({"doc_id": doc.id, "error": str(e)})
        time.sleep(0.1)   # API 부하 조절
    return failed
```

| 소유자 정보 | 처리 방법 |
|---|---|
| 팀 정보 있음 | 팀 admin → owner 부여 후 개별 이관 |
| 정보 없음 | `sensitivity=internal` 처리 후 수동 정제 |
| 양 너무 많음 | 신규 문서만 권한 적용, 구문서는 별도 컬렉션 분리 |

---

## 6. 운영 정책 요약

| 이벤트 | 처리 |
|---|---|
| 입사 | `team#member` tuple 자동 생성 |
| 퇴사 | 모든 tuple 즉시 삭제 (자동화 필수) |
| 팀 이동 | 기존 팀 삭제 + 신규 팀 추가 |
| 분기 감사 | `ListUsers` / `ListObjects` 로 전체 점검 |

---

## 7. 결정 사항 (2026-05-23)

| 항목 | 결정 | ADR |
|---|---|---|
| OpenFGA 호스팅 | Auth0 FGA (포트폴리오/개발) → 실운영 시 로컬 Docker 전환 | [ADR-0006-openfga-hosting.md](../docs/superpowers/decisions/ADR-0006-openfga-hosting.md) |
| `listObjects` 캐싱 | PostgreSQL TTL 캐시 (기존 POSTGRES_DSN 재사용, Redis 미도입) | [ADR-0009-fga-cache-postgresql.md](../docs/superpowers/decisions/ADR-0009-fga-cache-postgresql.md) |
| LLM | 현재 구현 유지 (Claude, langchain-anthropic) — 추상화로 교체 가능 | [ADR-0005-llm-selection.md](../docs/superpowers/decisions/ADR-0005-llm-selection.md) |
| 구문서 소유자 미지정 | 팀장 → CEO → super admin 순 fallback owner 지정 | [ADR-0004-legacy-doc-owner-policy.md](../docs/superpowers/decisions/ADR-0004-legacy-doc-owner-policy.md) |
