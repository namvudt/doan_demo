import { useEffect, useRef, useState, type ReactNode } from "react";
import { History, RefreshCw, Sparkles, X } from "lucide-react";
import { Badge } from "./Ui";

export function ChatWorkspace({
  children,
  history,
  modeLabel,
  historyCount,
  onRefreshHistory,
}: {
  children: ReactNode;
  history: ReactNode;
  modeLabel: string;
  historyCount: number;
  onRefreshHistory?: () => void;
}) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 760px)").matches,
  );
  const panel = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const update = () => setMobile(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!historyOpen) return;
    const previousOverflow = document.body.style.overflow;
    if (mobile) document.body.style.overflow = "hidden";
    close.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setHistoryOpen(false);
      }
      if (!mobile || event.key !== "Tab") return;
      const controls = Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          'a[href],button:not([disabled]),input:not([disabled]),[tabindex="0"]',
        ) || [],
      ).filter((element) => element.getClientRects().length > 0);
      const first = controls[0];
      const last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const returnTo = trigger.current;
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKey);
      if (returnTo?.isConnected) returnTo.focus({ preventScroll: true });
    };
  }, [historyOpen, mobile]);

  return (
    <div
      className={`chat-workspace chat-experience ${historyOpen ? "is-history-open" : ""}`}
    >
      <header className="chat-workspace-header">
        <div className="chat-workspace-title">
          <span className="chat-workspace-symbol">
            <Sparkles size={18} />
          </span>
          <strong>Hỏi đáp di sản</strong>
          <Badge tone="gold">{modeLabel}</Badge>
        </div>
        <div className="chat-toolbar-actions">
          <button
            ref={trigger}
            type="button"
            className="chat-toolbar-button"
            aria-label={historyOpen ? "Đóng lịch sử" : "Mở lịch sử"}
            aria-expanded={historyOpen}
            aria-controls="chat-history-panel"
            onClick={() => setHistoryOpen((value) => !value)}
          >
            <History size={17} /> <span>Lịch sử</span>
            {historyCount > 0 && (
              <span className="chat-history-count">{historyCount}</span>
            )}
          </button>
        </div>
      </header>
      <section className="chat-compose-column">{children}</section>
      {historyOpen && (
        <button
          type="button"
          className="chat-history-backdrop"
          aria-label="Đóng nền lịch sử"
          tabIndex={-1}
          onClick={() => setHistoryOpen(false)}
        />
      )}
      <aside
        ref={panel}
        id="chat-history-panel"
        className="chat-history-panel"
        hidden={!historyOpen}
        role={mobile && historyOpen ? "dialog" : undefined}
        aria-modal={mobile && historyOpen ? true : undefined}
        aria-labelledby="chat-history-title"
        onClick={(event) => {
          if ((event.target as HTMLElement).closest("a")) setHistoryOpen(false);
        }}
      >
        <div className="section-head chat-history-head">
          <div>
            <span className="eyebrow">{modeLabel}</span>
            <h2 id="chat-history-title">Lịch sử hỏi đáp</h2>
          </div>
          <div className="chat-toolbar-actions">
            {onRefreshHistory && (
              <button
                className="icon-button"
                aria-label="Tải lại"
                onClick={onRefreshHistory}
              >
                <RefreshCw size={17} />
              </button>
            )}
            <button
              ref={close}
              className="icon-button chat-history-close"
              aria-label="Đóng bảng lịch sử"
              onClick={() => setHistoryOpen(false)}
            >
              <X size={19} />
            </button>
          </div>
        </div>
        {history}
      </aside>
    </div>
  );
}
