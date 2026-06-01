"""ADR 인덱스 생성기.

`docs/superpowers/decisions/ADR-*.md` 각 파일의 제목과 `> **Status**:` 배지를 파싱해
같은 디렉토리의 `README.md` 인덱스 테이블을 재생성한다. README는 손으로 편집하지 말고
ADR 추가·상태 변경 후 이 스크립트를 실행할 것 (항상 ADR 파일과 동기화됨).

사용법: python -m scripts.gen_adr_index
"""
import re
from pathlib import Path

_DECISIONS = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "decisions"
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)
_STATUS_RE = re.compile(r"^>\s*\*\*Status\*\*:\s*(.+)$", re.M)
_LEGEND = "🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기"


def _num(path: Path) -> str:
    m = re.search(r"ADR-(\d+)", path.name)
    return m.group(1) if m else path.stem


def _badge(raw: str) -> str:
    """'🟢 적용완료 — 사유' → 이모지+라벨까지만 (사유/링크 절단)."""
    return re.split(r"\s+[—→]\s+", raw.strip(), maxsplit=1)[0].strip()


def build_index() -> str:
    rows = []
    for path in sorted(_DECISIONS.glob("ADR-*.md")):
        text = path.read_text(encoding="utf-8")
        tm = _TITLE_RE.search(text)
        sm = _STATUS_RE.search(text)
        title = tm.group(1).strip() if tm else path.stem
        title = re.sub(r"^(ADR-\d+:\s*|Decision:\s*)", "", title)
        status = _badge(sm.group(1)) if sm else "⚪ (미표기)"
        rows.append(f"| [{_num(path)}]({path.name}) | {title} | {status} |")

    lines = [
        "# ADR 인덱스",
        "",
        "> 자동 생성 파일 — 직접 편집 금지.",
        "> 갱신: `cd backend && .venv/bin/python -m scripts.gen_adr_index`",
        "",
        "| ADR | 제목 | 상태 |",
        "|-----|------|------|",
        *rows,
        "",
        "## 상태 범례",
        "",
        _LEGEND,
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    out = _DECISIONS / "README.md"
    out.write_text(build_index(), encoding="utf-8")
    print(f"생성 완료: {out} ({len(list(_DECISIONS.glob('ADR-*.md')))} ADR)")


if __name__ == "__main__":
    main()
