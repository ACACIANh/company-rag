import { useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github.css";
import type { Components } from "react-markdown";
import { rehypeCollapsibleFolders } from "./rehypeCollapsibleFolders";

function CopyableCodeBlock({ children }: { children: React.ReactNode }) {
  const handleCopy = useCallback(() => {
    const text =
      typeof children === "string"
        ? children
        : (children as React.ReactElement)?.props?.children ?? "";
    navigator.clipboard.writeText(String(text).trimEnd());
  }, [children]);

  return (
    <div className="relative group my-3">
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 hidden group-hover:flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-200 hover:bg-gray-600 transition-colors"
      >
        Copy
      </button>
      <pre className="overflow-x-auto rounded-lg border border-hairline text-sm">
        {children}
      </pre>
    </div>
  );
}

const components: Components = {
  pre({ children }) {
    return <CopyableCodeBlock>{children}</CopyableCodeBlock>;
  },
  code({ className, children }) {
    const isInline = !className;
    if (isInline) {
      return (
        <code className="bg-gray-100 text-pink-600 rounded px-1 py-0.5 text-[0.85em] font-mono">
          {children}
        </code>
      );
    }
    return <code className={className}>{children}</code>;
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3 rounded-lg border border-hairline text-[13px]">
        <table className="min-w-full border-collapse">{children}</table>
      </div>
    );
  },
  thead({ children }) {
    return (
      <thead className="bg-canvas-soft border-b border-hairline">{children}</thead>
    );
  },
  th({ children }) {
    return (
      <th className="px-3 py-2 text-left text-[11px] font-semibold text-ink-mute tracking-wide whitespace-nowrap">
        {children}
      </th>
    );
  },
  tbody({ children }) {
    return <tbody className="divide-y divide-hairline">{children}</tbody>;
  },
  tr({ children }) {
    return (
      <tr className="hover:bg-canvas-soft/60 transition-colors">{children}</tr>
    );
  },
  td({ children }) {
    return (
      <td className="px-3 py-2 text-ink align-top">{children}</td>
    );
  },
  details({ children }) {
    return <details className="my-2">{children}</details>;
  },
  summary({ children }) {
    return (
      <summary className="cursor-pointer select-none font-semibold text-ink mt-3 mb-1">
        {children}
      </summary>
    );
  },
};

export function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none leading-[1.6] text-[15px] font-light text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight, rehypeCollapsibleFolders]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
