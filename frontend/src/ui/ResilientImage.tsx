import { useState } from "react";
import { ImageOff, Landmark, RefreshCw } from "lucide-react";
import "./ResilientImage.css";

export type ResilientImageProps = {
  src?: string;
  alt: string;
  className?: string;
  loading?: "lazy" | "eager";
  label?: string;
  retryable?: boolean;
};

function ImageFrame({
  src,
  alt,
  className = "",
  loading = "lazy",
  label,
  retryable = true,
}: ResilientImageProps) {
  const [state, setState] = useState<"loading" | "loaded" | "error">(
    src ? "loading" : "error",
  );
  const [attempt, setAttempt] = useState(0);
  const source =
    attempt && src && !src.startsWith("blob:") && !src.startsWith("data:")
      ? `${src}${src.includes("?") ? "&" : "?"}image-retry=${attempt}`
      : src;

  return (
    <div
      className={`resilient-image ${state} ${className}`}
      aria-busy={state === "loading"}
    >
      {src && (
        <img
          key={attempt}
          src={source}
          alt={alt}
          loading={loading}
          decoding="async"
          onLoad={() => setState("loaded")}
          onError={() => setState("error")}
          hidden={state === "error"}
        />
      )}
      {state === "loading" && (
        <span className="image-loading" aria-hidden="true">
          <Landmark size={26} />
        </span>
      )}
      {state === "error" && (
        <div className="image-fallback" role="img" aria-label={alt}>
          <span className="image-fallback-symbol" aria-hidden="true">
            <Landmark size={34} />
          </span>
          <strong>{label || "Góc nhìn di sản"}</strong>
          <span>
            <ImageOff size={13} />
            {src ? "Ảnh đang tạm gián đoạn" : "Tư liệu ảnh đang được bổ sung"}
          </span>
          {src && retryable && (
            <button
              type="button"
              className="image-retry"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                setState("loading");
                setAttempt((value) => value + 1);
              }}
            >
              <RefreshCw size={13} /> Thử tải lại ảnh
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** A changed source gets fresh loading/error state, including cached images. */
export function ResilientImage(props: ResilientImageProps) {
  return <ImageFrame key={props.src || "no-image"} {...props} />;
}
