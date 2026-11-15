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

/** Generated answers are rendered as Markdown without raw HTML or remote images. */
export function Markdown({ children }: { children: string }) {
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
        {children}
      </ReactMarkdown>
    </div>
  );
}
