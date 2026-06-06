// 권한 스냅샷의 "접근 가능 폴더" 섹션(h3 + 바로 뒤 ul)을 네이티브 <details>로 감싸
// 기본 접힘 상태로 만든다. 매칭 키는 정확히 "접근 가능 폴더" h3 텍스트 — 이 문자열은
// 권한 스냅샷에만 나오므로 다른 메시지에는 영향이 없다. 별도 상태관리·라이브러리 없이
// 브라우저 기본 토글로 동작한다.

interface HastText {
  type: "text";
  value: string;
}

interface HastElement {
  type: "element";
  tagName: string;
  properties?: Record<string, unknown>;
  children: HastNode[];
}

type HastNode = HastElement | HastText | { type: string };

interface HastRoot {
  type: "root";
  children: HastNode[];
}

const FOLDER_HEADING = "접근 가능 폴더";

function isElement(node: HastNode): node is HastElement {
  return node.type === "element";
}

function textOf(node: HastElement): string {
  return node.children
    .map((child) => {
      if (child.type === "text") return (child as HastText).value;
      if (isElement(child)) return textOf(child);
      return "";
    })
    .join("")
    .trim();
}

export function rehypeCollapsibleFolders() {
  return (tree: HastRoot): void => {
    const children = tree.children;
    for (let i = 0; i < children.length; i++) {
      const node = children[i];
      if (!isElement(node) || node.tagName !== "h3") continue;
      if (textOf(node) !== FOLDER_HEADING) continue;

      // hast는 블록 요소 사이에 공백 텍스트 노드("\n")를 둔다 — 다음 "요소" 형제를 찾는다.
      let j = i + 1;
      while (j < children.length && !isElement(children[j])) j++;
      const next = children[j];
      if (!next || !isElement(next) || next.tagName !== "ul") continue;

      const count = next.children.filter(
        (child) => isElement(child) && child.tagName === "li",
      ).length;

      const details: HastElement = {
        type: "element",
        tagName: "details",
        properties: {},
        children: [
          {
            type: "element",
            tagName: "summary",
            properties: {},
            children: [{ type: "text", value: `${FOLDER_HEADING} (${count})` }],
          },
          next,
        ],
      };

      // h3 .. ul 구간(사이 공백 노드 포함)을 details 하나로 치환. open 속성 없음 → 기본 접힘.
      children.splice(i, j - i + 1, details);
    }
  };
}
