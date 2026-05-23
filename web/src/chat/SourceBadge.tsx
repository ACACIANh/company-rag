export function SourceBadge({ sources }: { sources: string[] }) {
  if (sources.length === 0) {
    return (
      <p className="text-[11px] text-ink-mute font-light">출처를 찾지 못했습니다.</p>
    );
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {sources.map((src) => (
        <span
          key={src}
          className="text-[10px] font-normal bg-primary-muted text-primary-deep px-2 py-0.5 rounded-pill tracking-[0.1px]"
          title={src}
        >
          {src}
        </span>
      ))}
    </div>
  );
}
