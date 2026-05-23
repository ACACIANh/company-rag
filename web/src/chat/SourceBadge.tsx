export function SourceBadge({ sources }: { sources: string[] }) {
  if (sources.length === 0) {
    return <p className="text-xs text-slate-400 mt-1">출처를 찾지 못했습니다.</p>;
  }
  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {sources.map((src) => (
        <span
          key={src}
          className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded"
          title={src}
        >
          {src}
        </span>
      ))}
    </div>
  );
}
