import {
  useId,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ArrowUpRight,
  ImagePlus,
  LoaderCircle,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { ResilientImage } from "./ResilientImage";
import { Button, Field } from "./Ui";

export type ChatComposerProps = {
  question: string;
  onQuestionChange: (question: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  questionLabel?: string;
  placeholder?: string;
  maxLength?: number;
  imageUrl?: string;
  imageAlt?: string;
  imageName?: string;
  imageHint?: string;
  imageBusy?: boolean;
  onFileChange: (file: File | null) => void;
  onRemoveImage?: () => void;
  maxUploadBytes?: number;
  sourceControl?: ReactNode;
  context?: ReactNode;
  audience?: {
    value: "tourist" | "student";
    onChange: (audience: "tourist" | "student") => void;
  };
  notice?: ReactNode;
  error?: string;
  auxiliaryAction?: ReactNode;
  busy?: boolean;
  disabled?: boolean;
  submitLabel?: string;
  busyLabel?: string;
  suggestions?: string[];
};

const imageTypes = new Set(["image/jpeg", "image/png", "image/webp"]);

/** Shared input presentation; upload, run ownership and model calls stay in pages. */
export function ChatComposer({
  question,
  onQuestionChange,
  onSubmit,
  questionLabel = "Câu hỏi",
  placeholder = "Bạn muốn tìm hiểu điều gì từ ảnh?",
  maxLength = 4000,
  imageUrl,
  imageAlt = "Ảnh đã chọn để hỏi",
  imageName,
  imageHint = "JPEG, PNG hoặc WebP · kéo thả hoặc chọn từ thiết bị",
  imageBusy = false,
  onFileChange,
  onRemoveImage,
  maxUploadBytes = 10 * 1_048_576,
  sourceControl,
  context,
  audience,
  notice,
  error,
  auxiliaryAction,
  busy = false,
  disabled = false,
  submitLabel = "Gửi câu hỏi",
  busyLabel = "Đang gửi…",
  suggestions = [],
}: ChatComposerProps) {
  const inputId = useId();
  const questionId = useId();
  const counterId = useId();
  const imageHintId = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const pickerButton = useRef<HTMLButtonElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [attachmentError, setAttachmentError] = useState("");
  const hasAttachment = Boolean(imageUrl || imageName);
  const cannotSubmit = busy || disabled || !question.trim();

  const selectFile = (file: File | undefined) => {
    if (!file || busy) return;
    if (!imageTypes.has(file.type)) {
      setAttachmentError("Hãy chọn ảnh JPEG, PNG hoặc WebP.");
      return;
    }
    if (!file.size) {
      setAttachmentError("Ảnh đang trống. Hãy chọn một tệp ảnh khác.");
      return;
    }
    if (file.size > maxUploadBytes) {
      setAttachmentError(
        `Ảnh vượt quá giới hạn ${Math.round((maxUploadBytes / 1_048_576) * 10) / 10} MB.`,
      );
      return;
    }
    setAttachmentError("");
    onFileChange(file);
  };

  const isFileDrag = (event: DragEvent) =>
    Array.from(event.dataTransfer.types).includes("Files");

  return (
    <>
      <form
        className="composer-card ai-composer"
        onSubmit={onSubmit}
        onKeyDown={(event) => {
          if (
            event.key === "Enter" &&
            (event.ctrlKey || event.metaKey) &&
            !event.nativeEvent.isComposing &&
            !cannotSubmit
          ) {
            event.preventDefault();
            event.currentTarget.requestSubmit();
          }
        }}
      >
        {context && <div className="ai-composer-context">{context}</div>}
        <div className="ai-composer-main">
          <div
            className={`ai-attachment-card ${imageUrl ? "has-image" : ""} ${dragging ? "is-dragging" : ""}`}
            data-testid="chat-image-dropzone"
            role="group"
            aria-label="Ảnh cho câu hỏi"
            aria-busy={imageBusy}
            onDragEnter={(event) => {
              if (!isFileDrag(event)) return;
              event.preventDefault();
              if (busy) return;
              dragDepth.current += 1;
              setDragging(true);
            }}
            onDragOver={(event) => {
              if (!isFileDrag(event)) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = busy ? "none" : "copy";
            }}
            onDragLeave={(event) => {
              if (!dragDepth.current) return;
              event.preventDefault();
              dragDepth.current -= 1;
              if (!dragDepth.current) setDragging(false);
            }}
            onDrop={(event) => {
              if (!isFileDrag(event)) return;
              event.preventDefault();
              dragDepth.current = 0;
              setDragging(false);
              selectFile(event.dataTransfer.files[0]);
            }}
          >
            <input
              ref={fileInput}
              id={inputId}
              className="sr-only ai-image-input"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              aria-label="Chọn ảnh để hỏi"
              aria-describedby={imageHintId}
              tabIndex={-1}
              disabled={busy}
              onChange={(event) => {
                selectFile(event.currentTarget.files?.[0]);
                // Re-selecting the same file must fire a fresh change event.
                event.currentTarget.value = "";
              }}
            />
            <button
              ref={pickerButton}
              className="ai-attachment-select"
              type="button"
              aria-label={hasAttachment ? "Đổi ảnh" : "Thêm ảnh"}
              aria-describedby={imageHintId}
              aria-controls={inputId}
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              {imageUrl ? (
                <ResilientImage
                  src={imageUrl}
                  alt={imageAlt}
                  loading="eager"
                  retryable={false}
                  className="ai-attachment-preview"
                />
              ) : (
                <span className="ai-attachment-icon" aria-hidden="true">
                  {imageBusy ? (
                    <LoaderCircle size={25} className="spin" />
                  ) : (
                    <ImagePlus size={25} />
                  )}
                </span>
              )}
              <span className="ai-attachment-copy">
                <strong>
                  {imageBusy
                    ? "Đang chuẩn bị ảnh…"
                    : imageName ||
                      (imageUrl ? "Ảnh đã chọn" : "Thêm một ảnh di sản")}
                </strong>
                <span id={imageHintId}>{imageHint}</span>
                <small>
                  {hasAttachment
                    ? "Chọn để đổi ảnh"
                    : "Chọn từ thiết bị hoặc kéo thả vào đây"}
                </small>
              </span>
              <span className="ai-attachment-action" aria-hidden="true">
                {hasAttachment ? (
                  <ImagePlus size={18} />
                ) : (
                  <ArrowUpRight size={18} />
                )}
              </span>
            </button>
            {hasAttachment && onRemoveImage && (
              <button
                type="button"
                className="ai-attachment-remove"
                aria-label="Bỏ ảnh đã chọn"
                disabled={busy}
                onClick={() => {
                  setAttachmentError("");
                  onRemoveImage();
                  pickerButton.current?.focus();
                }}
              >
                <X size={17} />
              </button>
            )}
          </div>
          <div className="ai-prompt-field">
            <div className="ai-prompt-label">
              <label htmlFor={questionId}>{questionLabel}</label>
              <span id={counterId}>
                {question.length}/{maxLength}
              </span>
            </div>
            <textarea
              id={questionId}
              rows={3}
              value={question}
              maxLength={maxLength}
              disabled={busy}
              onChange={(event) => onQuestionChange(event.target.value)}
              placeholder={placeholder}
              aria-describedby={counterId}
            />
          </div>
        </div>
        {(sourceControl || audience) && (
          <div className="ai-composer-options">
            {sourceControl && (
              <div className="ai-source-control">{sourceControl}</div>
            )}
            {audience && (
              <Field label="Đối tượng câu trả lời">
                <select
                  value={audience.value}
                  disabled={busy}
                  onChange={(event) =>
                    audience.onChange(
                      event.target.value as "tourist" | "student",
                    )
                  }
                >
                  <option value="tourist">Khách tham quan</option>
                  <option value="student">Học sinh/sinh viên</option>
                </select>
              </Field>
            )}
          </div>
        )}
        {(attachmentError || error) && (
          <p className="form-alert ai-composer-error" role="alert">
            {attachmentError || error}
          </p>
        )}
        <div className="composer-footer ai-composer-footer">
          <div className="ai-composer-notice">{notice}</div>
          <div className="ai-composer-actions">
            {auxiliaryAction}
            <Button type="submit" disabled={cannotSubmit}>
              {busy ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Send size={17} />
              )}
              {busy ? busyLabel : submitLabel}
            </Button>
          </div>
        </div>
        <span className="ai-send-shortcut">Ctrl / ⌘ + Enter để gửi</span>
      </form>
      {suggestions.length > 0 && (
        <div
          className="suggestion-row ai-suggestions"
          aria-label="Gợi ý câu hỏi"
        >
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={busy}
              onClick={() => onQuestionChange(suggestion.slice(0, maxLength))}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span>{suggestion}</span>
              <ArrowUpRight size={15} aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </>
  );
}
