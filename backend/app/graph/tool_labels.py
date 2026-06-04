"""사용 도구 라벨 계산 (응답 상단 헤더용).

route + agent_messages에서 실제 호출된 도구를 역할 라벨 목록으로 변환한다.
doc_search 라우트는 도구가 아니라 RAG 검색이므로 ["rag"]로 매핑한다(라벨 SSOT의 한 곳 예외).
agent 라우트는 tool_label_map()으로 도구명→라벨을 자동 변환한다(중복 제거, 첫 등장 순서 유지).
"""
from app.graph.tools.registry import tool_label_map


def collect_tool_labels(route: str, agent_messages: list) -> list[str]:
    if route == "doc_search":
        return ["rag"]
    if route != "agent":
        return []
    label_map = tool_label_map()
    labels: list[str] = []
    for msg in agent_messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            label = label_map.get(name)
            if label and label not in labels:
                labels.append(label)
    return labels
