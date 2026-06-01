# 권한 RAG 설계 (목표 상태)

## 원칙
- pre-filter 방식: 권한 통과 폴더를 먼저 받고, 그 범위에서만 벡터 검색
- 개인 단위 메타데이터 없음. 권한 주체는 부서 단위
- 폴더 권한은 트리 상속

## 인덱싱
- 청크 메타데이터에 path를 경로 형태로 저장 (예: /projects/friday)

## OpenFGA 모델
type user
type department
  relations
    define member: [user]
type folder
  relations
    define parent: [folder]
    define viewer: [department#member]
    define can_read: viewer or can_read from parent

## 검색 흐름
1. OpenFGA ListObjects로 사용자가 can_read 가능한 folder 목록을 받음
2. 목록에서 상위 노드만 추림 (부모가 있으면 자식 경로는 버림)
3. vectorstore에서 추린 path 목록에 prefix 매칭되는 청크만 pre-filter한 뒤, 그 범위에서 벡터 검색
4. 통과한 청크만 LLM에 전달해 답변 생성