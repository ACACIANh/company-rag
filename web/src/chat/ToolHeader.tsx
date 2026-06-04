export function ToolHeader({ tools }: { tools: string[] }) {
  if (!tools || tools.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-1 px-1">
      <span className="text-[10px] text-ink-mute font-light">🔧 도구</span>
      {tools.map((t) => (
        <span
          key={t}
          title={t}
          className="text-[10px] font-normal bg-primary-muted text-primary-deep px-2 py-0.5 rounded-pill tracking-[0.1px] uppercase"
        >
          {t}
        </span>
      ))}
    </div>
  );
}
