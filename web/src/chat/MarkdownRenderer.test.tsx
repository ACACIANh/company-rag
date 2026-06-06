import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MarkdownRenderer } from "./MarkdownRenderer";

const SNAPSHOT = `## 권한 스냅샷

**사용자**: user-daesu

### 접근 가능 폴더
- /company/hr
- /company
- /company/common

### 접근 가능 테이블
employees
`;

describe("MarkdownRenderer — 권한 스냅샷 폴더 접기", () => {
  it("폴더 섹션을 기본 접힘(<details>, open 없음)으로 감싸고 개수를 요약한다", () => {
    const { container } = render(<MarkdownRenderer content={SNAPSHOT} />);

    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details!.hasAttribute("open")).toBe(false); // 기본 접힘

    const summary = details!.querySelector("summary");
    expect(summary?.textContent).toBe("접근 가능 폴더 (3)");

    // 폴더 항목은 접혀 있어도 DOM에는 존재한다.
    const items = details!.querySelectorAll("li");
    expect(items.length).toBe(3);
    expect(details!.textContent).toContain("/company/hr");
  });

  it("폴더 섹션 외 다른 섹션(테이블)은 <details>로 감싸지 않는다", () => {
    const { container } = render(<MarkdownRenderer content={SNAPSHOT} />);

    const headings = Array.from(container.querySelectorAll("h3")).map(
      (h) => h.textContent,
    );
    expect(headings).toContain("접근 가능 테이블"); // 그대로 h3
    expect(headings).not.toContain("접근 가능 폴더"); // summary로 치환됨
  });

  it("폴더 섹션이 없는 일반 메시지는 <details>를 만들지 않는다", () => {
    const { container } = render(
      <MarkdownRenderer content={"# 안녕하세요\n\n- 항목1\n- 항목2"} />,
    );
    expect(container.querySelector("details")).toBeNull();
  });
});
