import type { Scene, SceneKind } from "./lib/types";

const KIND_DESC: Record<SceneKind, string> = {
  capability: "AI 도우미 소개 — 무엇을 도와주나",
  permission: "내 권한 조회",
  rag: "사내 문서 검색(RAG)",
  rag_block: "권한 밖 문서 접근 → FGA 차단",
  clarify: "모호한 질문 → 재질문(HITL)",
  sql_read: "SQL 조회 — 실행 사유 승인(HITL)",
  sql_write: "SQL 변경 — 실행 사유 승인(HITL)",
  sql_write_deny: "권한 밖 SQL 변경 → 거부(DENY)",
  permission_delegate: "부서 멤버십 위임 — 사유 승인(HITL)",
  audit: "감사 로그 — 활동 이력 추적",
};

// 서사 흐름상 기본 문구로 부족한 장면만 오버라이드.
const ID_OVERRIDE: Record<string, string> = {
  "10": "법무 문서 열람 권한 부여(HITL)",
  "12": "권한 부여 즉시 반영 — 차단됐던 문서 접근 성공",
  "13": "부서 위임 전 — 권한 확인(before)",
  "15": "부서 위임 후 — 권한 재확인",
};

export function captionFor(scene: Scene): string {
  const who = scene.dept ? `${scene.display_name}(${scene.dept})` : scene.display_name;
  const desc = ID_OVERRIDE[scene.id] ?? KIND_DESC[scene.kind];
  return `장면 ${scene.id} · ${who} · ${desc}`;
}
