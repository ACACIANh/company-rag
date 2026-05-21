# Qdrant Vector Store 추가 설계

**날짜:** 2026-05-21  
**대상:** `shared/vector_store`

## 개요

현재 ChromaDB만 지원하는 vector store에 Qdrant Cloud를 추가한다. 기존 `VectorStore` ABC와 ChromaStore 패턴을 그대로 따르는 최소 변경 방식으로 구현한다.

## 아키텍처

기존 패턴과 완전히 대칭적인 구조:

```
shared/vector_store/
├── base.py              # VectorStore ABC (변경 없음)
├── chroma_store.py      # 기존 ChromaStore (변경 없음)
├── qdrant_store.py      # 신규: QdrantStore
├── factory.py           # vector_store="qdrant" 분기 추가
└── adapters/
    └── langchain_retriever.py  # 변경 없음
```

## 변경 상세

### 1. `shared/vector_store/qdrant_store.py` (신규)

`QdrantStore(VectorStore)` 클래스 구현:

- `__init__(url, api_key, collection)`: `QdrantClient` 연결, collection 없으면 자동 생성
- `add(chunks, embeddings)`: `PointStruct` 리스트로 변환 후 `upsert`
- `search(query_embedding, top_k)`: `query_points`로 유사도 검색, `SearchResult` 반환
- `count()`: `get_collection` API로 벡터 수 반환

score 변환: Qdrant는 cosine similarity를 직접 반환하므로 `1 - distance` 변환 불필요.

### 2. `shared/config.py`

`Config` dataclass에 필드 추가:

```python
qdrant_url: str          # QDRANT_URL 환경변수
qdrant_api_key: str      # QDRANT_API_KEY 환경변수
qdrant_collection: str   # QDRANT_COLLECTION 환경변수, 기본값 "documents"
```

### 3. `shared/vector_store/factory.py`

```python
if config.vector_store == "qdrant":
    return QdrantStore(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection=config.qdrant_collection,
    )
```

### 4. `requirements.txt`

```
qdrant-client>=1.7.0
```

## 환경변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `VECTOR_STORE` | 아니오 | `chroma` | `qdrant`로 설정 시 QdrantStore 사용 |
| `QDRANT_URL` | Qdrant 사용 시 | — | Qdrant Cloud endpoint URL |
| `QDRANT_API_KEY` | Qdrant 사용 시 | — | Qdrant Cloud API key |
| `QDRANT_COLLECTION` | 아니오 | `documents` | 사용할 collection 이름 |

## 테스트 전략

`tests/shared/test_vector_store.py`에 `QdrantStore` 단위 테스트 추가:

- `QdrantClient`를 `unittest.mock.MagicMock`으로 mock
- `add`, `search`, `count` 각 메서드 동작 검증
- factory가 `vector_store="qdrant"` 설정에서 `QdrantStore`를 반환하는지 검증

실제 Qdrant Cloud 연결 테스트는 범위 밖 (integration test 별도 구성 필요).

## 영향 범위

- 기존 ChromaStore, 모든 workflow 코드: **변경 없음**
- `VECTOR_STORE=chroma`(기본값) 유지 시 동작 동일
