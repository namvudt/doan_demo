import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function safeHref(value?: string) {
  if (!value) return undefined;
  if (value.startsWith("#")) return value;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

export type MarkdownSourceRef = {
  source_id: string;
  title: string;
  url?: string | null;
};

function linkifyCitations(text: string, sources?: MarkdownSourceRef[]) {
  if (!sources?.length) return text;
  const lookup = new Map<
    string,
    { index: number; title: string; href: string }
  >();
  sources.forEach((source, index) => {
    const href = safeHref(source.url || undefined) || `#source-${source.source_id}`;
    lookup.set(source.source_id, {
      index: index + 1,
      title: source.title || source.source_id,
      href,
    });
  });
  return text.replace(
    /\[((?:wiki|web)_[A-Za-z0-9_-]+)\](?!\()/g,
    (match, id: string) => {
      const target = lookup.get(id);
      if (!target) return match;
      const cleanTitle = target.title.replace(/[\[\]]/g, "");
      return `[${target.index}. ${cleanTitle}](${target.href})`;
    },
  );
}

/** Generated answers are rendered as Markdown without raw HTML or remote images. */
export function Markdown({
  children,
  sources,
}: {
  children: string;
  sources?: MarkdownSourceRef[];
}) {
  const content = linkifyCitations(children, sources);
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children: label }) => {
            const safe = safeHref(href);
            if (!safe) return <span>{label}</span>;
            return safe.startsWith("#") ? (
              <a href={safe}>{label}</a>
            ) : (
              <a href={safe} target="_blank" rel="noopener noreferrer">
                {label}
              </a>
            );
          },
          img: () => (
            <span className="inline-notice">
              Ảnh ngoài trong nội dung đã được ẩn.
            </span>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
