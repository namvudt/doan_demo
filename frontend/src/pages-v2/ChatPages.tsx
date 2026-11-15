import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  Archive,
  BookHeart,
  CheckCircle2,
  ChevronDown,
  CircleStop,
  Download,
  FileImage,
  ImagePlus,
  Info,
  Landmark,
  MessageSquareText,
  RefreshCw,
  RotateCcw,
  SearchCheck,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Upload,
  Workflow,
  X,
} from "lucide-react";
import {
  ApiError,
  createIdempotencyKey,
  evaluateRunModelMode,
  isExecutionTerminal,
} from "../api/contracts";
import type {
  AssetView,
  EventView,
  FeedbackBody,
  MetricsView,
  PreflightView,
  ResultView,
  RetrievedSource,
  RunView,
  StepsView,
  WorkflowView,
} from "../api/schema";
import { useApp } from "../app/AppContext";
import { usePreview } from "../preview/PreviewProvider";
import { Markdown } from "../ui/Markdown";
import { Badge, Button, EmptyState, Field, StatusCard } from "../ui/Ui";
import { ResilientImage } from "../ui/ResilientImage";
import "../ui/chat-experience.css";

type PreviewRun = {
  id: string;
  question: string;
  answer: string;
  heritageId?: string;
  imageName?: string;
  createdAt: string;
  status: "reviewed" | "insufficient_evidence";
  stages: Array<{
    id: string;
    title: string;
    status: "completed" | "skipped";
    summary: string;
  }>;
};

const PREVIEW_RUNS_KEY = "heritage.ui-preview.runs.v1";
function readPreviewRuns(): PreviewRun[] {
  try {
    return JSON.parse(
      sessionStorage.getItem(PREVIEW_RUNS_KEY) || "[]",
    ) as PreviewRun[];
  } catch {
    return [];
  }
}
function savePreviewRun(run: PreviewRun) {
  const runs = [run, ...readPreviewRuns()].slice(0, 20);
  sessionStorage.setItem(PREVIEW_RUNS_KEY, JSON.stringify(runs));
}

const executionLabels: Record<string, string> = {
  queued: "Đang chờ",
  running: "Đang xử lý",
  cancel_requested: "Đang yêu cầu hủy",
  succeeded: "Đã chạy xong",
  failed: "Thất bại",
  cancelled: "Đã hủy",
};
const resultLabels: Record<string, string> = {
  reviewed: "Đã được đánh giá tự động",
  unverified: "Chưa hoàn tất đánh giá",
  insufficient_evidence: "Chưa đủ bằng chứng",
  out_of_scope: "Ngoài phạm vi hỗ trợ",
  failed: "Kết quả gặp lỗi",
};

function LiveModelConsent() {
  const app = useApp();
  if (app.capabilities?.model_mode !== "live" || !app.allowLiveModelCalls)
    return null;
  return (
    <StatusCard kind="warning" title="AI thật · Có thể phát sinh chi phí">
      <p>
        Ảnh và câu hỏi sẽ được gửi tới model do server cấu hình. Mỗi lần tạo,
        retry hoặc review là một tác vụ riêng; frontend không tự chạy lại tác vụ
        trả phí.
      </p>
      <label className="live-model-consent">
        <input
          type="checkbox"
          checked={app.liveModelConsent}
          onChange={(event) => app.setLiveModelConsent(event.target.checked)}
        />
        <span>
          Tôi đồng ý gọi AI thật trong phiên này và chấp nhận chi phí phát sinh.
        </span>
      </label>
    </StatusCard>
  );
}

function PreviewChat() {
  const preview = usePreview();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const heritage = preview.heritages.find(
    (item) => item.id === params.get("heritage"),
  );
  const [question, setQuestion] = useState(
    heritage
      ? `Hãy giới thiệu những thông tin có căn cứ về ${heritage.name}.`
      : "",
  );
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [fileUrl, setFileUrl] = useState<string>();
  useEffect(() => {
    if (!file) {
      setFileUrl(undefined);
      return;
    }
    const url = URL.createObjectURL(file);
    setFileUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const previewUrl = fileUrl || heritage?.media[0]?.url;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    window.setTimeout(() => {
      const sources = heritage
        ? preview.contentSources.filter((source) =>
            heritage.sourceIds.includes(source.id),
          )
        : [];
      const evidence = heritage
        ? `${heritage.introduction}${heritage.history ? `\n\n${heritage.history}` : ""}`
        : "Ảnh và câu hỏi này chưa liên kết với hồ sơ minh họa. UI Preview không thực sự phân tích ảnh hoặc gọi mô hình.";
      const answer = `> **Kết quả mô phỏng — không phải phân tích AI thật**\n\n${evidence}\n\n${sources.length ? `Nguồn metadata minh họa: ${sources.map((source) => `[${source.title}](${source.url})`).join(", ")}.` : "Chưa có nguồn metadata để đối chiếu."}`;
      const run: PreviewRun = {
        id: `preview-${crypto.randomUUID()}`,
        question: question.trim(),
        answer,
        heritageId: heritage?.id,
        imageName: file?.name || heritage?.media[0]?.alt,
        createdAt: new Date().toISOString(),
        status: sources.length ? "reviewed" : "insufficient_evidence",
        stages: [
          {
            id: "scope",
            title: "Kiểm tra đầu vào",
            status: "completed",
            summary: "Đầu vào mô phỏng hợp lệ.",
          },
          {
            id: "coordinate",
            title: "Lập kế hoạch",
            status: "completed",
            summary: "Đã tạo kế hoạch mô phỏng.",
          },
          {
            id: "visual",
            title: "Quan sát ảnh",
            status: file || heritage?.media.length ? "completed" : "skipped",
            summary:
              file || heritage?.media.length
                ? "Không phân tích thật; chỉ ghi nhận có ảnh."
                : "Không có ảnh.",
          },
          {
            id: "knowledge",
            title: "Tra cứu tư liệu",
            status: sources.length ? "completed" : "skipped",
            summary: sources.length
              ? "Dùng metadata fixture được liên kết."
              : "Không có nguồn liên kết.",
          },
          {
            id: "aggregate",
            title: "Tổng hợp bản nháp",
            status: "completed",
            summary: "Tổng hợp dữ liệu Preview.",
          },
          {
            id: "judge",
            title: "Đánh giá câu trả lời",
            status: sources.length ? "completed" : "skipped",
            summary: sources.length
              ? "Đánh giá mô phỏng."
              : "Chưa đủ chứng cứ.",
          },
        ],
      };
      savePreviewRun(run);
      setBusy(false);
      navigate(`/chat/runs/${run.id}`);
    }, 650);
  };
  return (
    <div className="chat-workspace">
      <section className="chat-compose-column">
        <header className="chat-heading">
          <span className="eyebrow">HỎI ĐÁP HÌNH ẢNH</span>
          <h1>Một bức ảnh, nhiều lớp câu chuyện</h1>
          <p>
            Đặt câu hỏi rõ ràng và kiểm tra trạng thái đánh giá cùng nguồn hỗ
            trợ.
          </p>
        </header>
        {heritage && (
          <div className="context-chip">
            <Landmark size={16} />
            <span>
              <small>Ngữ cảnh Preview</small>
              <strong>{heritage.name}</strong>
            </span>
            <Link to="/chat" aria-label="Bỏ ngữ cảnh">
              <X size={15} />
            </Link>
          </div>
        )}
        <form className="composer-card" onSubmit={submit}>
          <label className={`image-dropzone ${previewUrl ? "has-image" : ""}`}>
            {previewUrl ? (
              <>
                <ResilientImage
                  src={previewUrl}
                  alt="Ảnh đã chọn để hỏi"
                  loading="eager"
                  retryable={false}
                />
                <span className="image-overlay">
                  <ImagePlus size={18} /> Đổi ảnh
                </span>
              </>
            ) : (
              <>
                <ImagePlus size={28} />
                <strong>Chọn một ảnh di sản</strong>
                <span>JPEG, PNG hoặc WebP · chỉ mô phỏng trong Preview</span>
              </>
            )}
            <input
              className="sr-only"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <Field
            label="Bạn muốn tìm hiểu điều gì?"
            hint={`${question.length}/4000 ký tự`}
          >
            <textarea
              rows={5}
              maxLength={4000}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ví dụ: Những chi tiết kiến trúc nào có thể quan sát trong ảnh?"
            />
          </Field>
          <div className="composer-footer">
            <p>
              <Info size={14} /> Preview không gọi AI, không xác minh ảnh và
              không lưu backend.
            </p>
            <Button type="submit" disabled={busy || !question.trim()}>
              {busy ? "Đang mô phỏng…" : "Khám phá"}
              <Send size={16} />
            </Button>
          </div>
        </form>
        <div className="suggestion-row">
          <span>Gợi ý:</span>
          {[
            "Mô tả chi tiết nhìn thấy trong ảnh",
            "Thông tin nào cần kiểm chứng thêm?",
            "Các nguồn nào đang hỗ trợ câu trả lời?",
          ].map((text) => (
            <button key={text} onClick={() => setQuestion(text)}>
              {text}
            </button>
          ))}
        </div>
      </section>
      <aside className="chat-history-panel">
        <div className="section-head">
          <div>
            <span className="eyebrow">LỊCH SỬ PREVIEW</span>
            <h2>Run gần đây</h2>
          </div>
        </div>
        {readPreviewRuns().length ? (
          <div className="history-list">
            {readPreviewRuns().map((run) => (
              <Link to={`/chat/runs/${run.id}`} key={run.id}>
                <MessageSquareText size={16} />
                <span>
                  <strong>{run.question}</strong>
                  <small>
                    {new Date(run.createdAt).toLocaleString("vi-VN")}
                  </small>
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Chưa có run"
            icon={<MessageSquareText size={26} />}
          >
            Kết quả mô phỏng trong tab này sẽ xuất hiện ở đây.
          </EmptyState>
        )}
      </aside>
    </div>
  );
}

function ApiChat() {
  const app = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [question, setQuestion] = useState("");
  const [audience, setAudience] = useState<"tourist" | "student">("tourist");
  const [file, setFile] = useState<File | null>(null);
  const [selectedSample, setSelectedSample] = useState(
    params.get("sample") || "",
  );
  const [asset, setAsset] = useState<AssetView | null>(null);
  const [imageUrl, setImageUrl] = useState<string>();
  const [runs, setRuns] = useState<RunView[]>([]);
  const [loading, setLoading] = useState(false);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [error, setError] = useState("");
  const [preflight, setPreflight] = useState<PreflightView | null>(null);
  const [checking, setChecking] = useState(false);
  const createIntent = useRef<{ fingerprint: string; key: string } | null>(
    null,
  );
  const gate = evaluateRunModelMode(app.capabilities, {
    allowLiveModelCalls: app.allowLiveModelCalls,
    liveModelConsent: app.liveModelConsent,
  });

  const loadRuns = useCallback(async () => {
    if (!app.apiSession) return setRuns([]);
    try {
      setRuns((await app.api.runs({ limit: 12 })).items);
    } catch {
      /* surfaced by actions */
    }
  }, [app.api, app.apiSession]);
  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const sessionId = app.apiSession?.session_id;
  useEffect(() => {
    if (!selectedSample || !sessionId) {
      setSampleLoading(false);
      return;
    }
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setSampleLoading(true);
    setError("");
    void (async () => {
      try {
        const selectedAsset = await app.api.useSample(
          selectedSample,
          controller.signal,
        );
        const blob = await app.api.assetContent(
          selectedAsset.asset_id,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setAsset(selectedAsset);
        setImageUrl(objectUrl);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Không tải được ảnh mẫu. Hãy chọn lại hoặc tải ảnh của bạn.",
          );
        }
      } finally {
        if (!controller.signal.aborted) setSampleLoading(false);
      }
    })();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [app.api, selectedSample, sessionId]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!app.apiSession)
      return navigate("/login", { state: { from: "/chat" } });
    if (!gate.allowed) return setError(gate.message);
    if (!question.trim()) return setError("Hãy nhập câu hỏi.");
    if (sampleLoading) return;
    if (!asset && !file && !selectedSample)
      return setError("Hãy tải ảnh hoặc chọn sample thật từ backend.");
    setLoading(true);
    try {
      let activeAsset = asset;
      if (!activeAsset && file) activeAsset = await app.api.uploadAsset(file);
      if (!activeAsset && selectedSample)
        activeAsset = await app.api.useSample(selectedSample);
      if (!activeAsset) throw new Error("Không tạo được asset.");
      setAsset(activeAsset);
      const fingerprint = JSON.stringify({
        asset_id: activeAsset.asset_id,
        question: question.trim(),
        audience,
      });
      if (createIntent.current?.fingerprint !== fingerprint) {
        createIntent.current = {
          fingerprint,
          key: createIdempotencyKey("create-run"),
        };
      }
      const run = await app.api.createRun(
        {
          asset_id: activeAsset.asset_id,
          question: question.trim(),
          audience,
          profile: "default",
        },
        createIntent.current.key,
      );
      createIntent.current = null;
      navigate(`/chat/runs/${run.run_id}`);
    } catch (reason) {
      const apiError = reason instanceof ApiError ? reason : null;
      setError(
        `${reason instanceof Error ? reason.message : "Không thể tạo run."}${apiError?.requestId ? ` · Request ID: ${apiError.requestId}` : ""}`,
      );
    } finally {
      setLoading(false);
    }
  };

  const checkReadiness = async () => {
    setChecking(true);
    setError("");
    try {
      setPreflight(await app.api.preflight({}));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Không kiểm tra được readiness.",
      );
    } finally {
      setChecking(false);
    }
  };

  if (!app.apiSession)
    return (
      <div className="page-shell">
        <header className="page-heading">
          <div>
            <span className="eyebrow">API INTEGRATION</span>
            <h1>Hỏi đáp hình ảnh</h1>
          </div>
        </header>
        <EmptyState title="Cần một phiên khách" icon={<Archive size={28} />}>
          Tạo hoặc gắn guest access token để sở hữu asset và run.{" "}
          <Link to="/login">Truy cập phiên khách</Link>.
        </EmptyState>
      </div>
    );
  return (
    <div className="chat-workspace api-chat-workspace">
      <section className="chat-compose-column">
        <header className="chat-heading">
          <span className="eyebrow">API INTEGRATION · MULTI-AGENT VQA</span>
          <h1>Hỏi backend bằng một ảnh</h1>
          <p>
            {app.capabilities?.model_mode === "live"
              ? "Đang kết nối AI thật theo cấu hình server. Kiểm tra sẵn sàng và xác nhận chi phí trước khi bắt đầu."
              : "Backend sẽ xử lý ảnh và câu hỏi; chế độ demo sử dụng kết quả AI mô phỏng."}
          </p>
        </header>
        <LiveModelConsent />
        {!gate.allowed && (
          <StatusCard
            kind={
              gate.code === "LIVE_MODEL_CONSENT_REQUIRED" ? "warning" : "error"
            }
            title="Đã khóa thao tác tạo run"
          >
            {gate.message}
          </StatusCard>
        )}
        {preflight && (
          <StatusCard
            kind={preflight.ready ? "success" : "warning"}
            title={
              preflight.ready
                ? "Các role đã sẵn sàng theo preflight"
                : "Một số role chưa sẵn sàng"
            }
          >
            {preflight.roles
              .map(
                (role) =>
                  `${role.role}: ${role.ready ? "ready" : role.error_code || "not ready"}`,
              )
              .join(" · ")}
            <br />
            <span className="small">
              Preflight không xác minh quota sinh nội dung.
            </span>
          </StatusCard>
        )}
        {params.get("heritage") && (
          <StatusCard
            kind="info"
            title="Ngữ cảnh di sản không được gửi tới API"
          >
            Backend không hỗ trợ <code>heritage_id</code>. Hãy chọn/tải một
            asset thật và đặt câu hỏi có nội dung đầy đủ.
          </StatusCard>
        )}
        <form className="composer-card" onSubmit={submit}>
          <div className="api-image-picker">
            <label className={`image-dropzone ${imageUrl ? "has-image" : ""}`}>
              {imageUrl ? (
                <>
                  <ResilientImage
                    src={imageUrl}
                    alt="Ảnh tải lên"
                    loading="eager"
                    retryable={false}
                  />
                  <span className="image-overlay">
                    <Upload size={17} /> Đổi ảnh
                  </span>
                </>
              ) : (
                <>
                  <Upload size={27} />
                  <strong>Tải ảnh của bạn</strong>
                  <span>
                    JPEG, PNG, WebP · tối đa{" "}
                    {app.capabilities
                      ? Math.round(
                          app.capabilities.max_upload_bytes / 1_048_576,
                        )
                      : "?"}{" "}
                    MB
                  </span>
                </>
              )}
              <input
                className="sr-only"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  setAsset(null);
                  setSelectedSample("");
                }}
              />
            </label>
            <div className="or-divider">
              <span>hoặc</span>
            </div>
            <Field label="Sample thật từ backend">
              <select
                value={selectedSample}
                onChange={(e) => {
                  setSelectedSample(e.target.value);
                  setFile(null);
                  setAsset(null);
                  setImageUrl(undefined);
                }}
              >
                <option value="">Chọn sample…</option>
                {app.apiSamples.map((sample) => (
                  <option value={sample.sample_id} key={sample.sample_id}>
                    {sample.title}
                  </option>
                ))}
              </select>
            </Field>
            {sampleLoading && (
              <p className="small muted" role="status">
                Đang chuẩn bị ảnh mẫu của bạn…
              </p>
            )}
          </div>
          <div className="form-grid-2 composer-fields">
            <Field
              label="Câu hỏi"
              hint={`${question.length}/${app.capabilities?.max_question_characters || 4000}`}
            >
              <textarea
                rows={5}
                maxLength={app.capabilities?.max_question_characters || 4000}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Bạn muốn tìm hiểu điều gì từ ảnh?"
              />
            </Field>
            <Field label="Đối tượng câu trả lời">
              <select
                value={audience}
                onChange={(e) =>
                  setAudience(e.target.value as "tourist" | "student")
                }
              >
                <option value="tourist">Khách tham quan</option>
                <option value="student">Học sinh/sinh viên</option>
              </select>
            </Field>
          </div>
          {error && (
            <p className="form-alert" role="alert">
              {error}
            </p>
          )}
          <div className="composer-footer">
            <p>
              <Info size={14} /> Không có conversation_id hay heritage_id trong
              request.
            </p>
            <div className="button-row">
              <Button
                type="button"
                tone="secondary"
                onClick={checkReadiness}
                disabled={checking}
              >
                {checking ? "Đang kiểm tra…" : "Kiểm tra sẵn sàng"}
              </Button>
              <Button
                type="submit"
                disabled={loading || sampleLoading || !gate.allowed}
              >
                {loading ? "Đang tạo run…" : "Tạo run"}
                <Send size={16} />
              </Button>
            </div>
          </div>
        </form>
      </section>
      <aside className="chat-history-panel">
        <div className="section-head">
          <div>
            <span className="eyebrow">RUN CỦA PHIÊN</span>
            <h2>Lịch sử backend</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Tải lại"
            onClick={loadRuns}
          >
            <RefreshCw size={16} />
          </button>
        </div>
        {runs.length ? (
          <div className="history-list">
            {runs.map((run) => (
              <Link to={`/chat/runs/${run.run_id}`} key={run.run_id}>
                <span className={`status-dot ${run.execution_status}`} />
                <span>
                  <strong>{run.question}</strong>
                  <small>
                    {executionLabels[run.execution_status]} ·{" "}
                    {new Date(run.created_at).toLocaleString("vi-VN")}
                  </small>
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Chưa có run"
            icon={<MessageSquareText size={26} />}
          >
            Run thuộc phiên khách này sẽ xuất hiện ở đây.
          </EmptyState>
        )}
      </aside>
    </div>
  );
}

export function ChatPage() {
  const app = useApp();
  return app.mode === "preview" ? <PreviewChat /> : <ApiChat />;
}

function PreviewRunDetail({ runId }: { runId: string }) {
  const preview = usePreview();
  const app = useApp();
  const run = readPreviewRuns().find((item) => item.id === runId);
  if (!run)
    return (
      <div className="page-shell">
        <EmptyState
          title="Không tìm thấy run Preview"
          icon={<MessageSquareText size={27} />}
        >
          Run mô phỏng chỉ giữ trong tab hiện tại.{" "}
          <Link to="/chat">Tạo run mới</Link>.
        </EmptyState>
      </div>
    );
  const feedback = (rating: "helpful" | "needs_review") => {
    preview.submitFeedback({
      runId: run.id,
      rating,
      note:
        rating === "helpful"
          ? "Phản hồi hữu ích từ trang kết quả Preview."
          : "Cần kiểm tra lại kết quả mô phỏng.",
    });
    app.notify("Đã lưu phản hồi trong UI Preview, chưa gửi backend.");
  };
  return (
    <div className="run-page page-shell">
      <header className="run-header">
        <div>
          <span className="eyebrow">KẾT QUẢ UI PREVIEW</span>
          <h1>{run.question}</h1>
          <div className="detail-badges">
            <Badge tone="green">Đã mô phỏng</Badge>
            <Badge tone={run.status === "reviewed" ? "green" : "gold"}>
              {resultLabels[run.status]}
            </Badge>
          </div>
        </div>
        <Link to="/chat" className="button secondary">
          <MessageSquareText size={16} /> Câu hỏi mới
        </Link>
      </header>
      <div className="run-layout">
        <main className="answer-column">
          <section className="answer-card">
            <div className="answer-card-head">
              <span>
                <Sparkles size={18} /> Câu trả lời
              </span>
              <Badge tone="gold">Mô phỏng</Badge>
            </div>
            <Markdown>{run.answer}</Markdown>
          </section>
          <section className="feedback-card">
            <div>
              <strong>Kết quả mô phỏng này có rõ ràng không?</strong>
              <p>Phản hồi chỉ xuất hiện trong khu vực quản trị Preview.</p>
            </div>
            <div>
              <Button tone="secondary" onClick={() => feedback("helpful")}>
                <ThumbsUp size={16} /> Hữu ích
              </Button>
              <Button tone="secondary" onClick={() => feedback("needs_review")}>
                <ThumbsDown size={16} /> Cần xem lại
              </Button>
            </div>
          </section>
        </main>
        <aside className="execution-column">
          <section className="panel">
            <div className="section-head">
              <div>
                <span className="eyebrow">THỰC THI</span>
                <h2>Workflow stages</h2>
              </div>
            </div>
            <div className="stage-list">
              {run.stages.map((stage) => (
                <div key={stage.id} className={stage.status}>
                  <span>
                    {stage.status === "completed" ? (
                      <CheckCircle2 size={16} />
                    ) : (
                      <CircleStop size={16} />
                    )}
                  </span>
                  <div>
                    <strong>{stage.title}</strong>
                    <p>{stage.summary}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section className="panel limitation-panel">
            <h3>Model calls / attempts</h3>
            <p>Dữ liệu Preview không gọi model.</p>
            <h3>Tool / API calls</h3>
            <p>Không có trace tool; frontend không dựng lại dữ liệu giả.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}

type ApiRunState = {
  run?: RunView;
  events: EventView[];
  result?: ResultView;
  sources: RetrievedSource[];
  steps?: StepsView;
  metrics?: MetricsView;
  feedback?: FeedbackBody;
  workflow?: WorkflowView;
  loading: boolean;
  error?: string;
};

function useApiRun(runId: string) {
  const { api, apiSession } = useApp();
  const [state, setState] = useState<ApiRunState>({
    events: [],
    sources: [],
    loading: true,
  });
  const refresh = useCallback(async () => {
    if (!apiSession) return;
    try {
      const run = await api.run(runId);
      const [history, sources, steps, metrics, feedback, workflow] =
        await Promise.all([
          api.eventHistory(runId, { after: 0, limit: 500 }),
          api.sources(runId),
          api.steps(runId),
          api.metrics(runId),
          api.feedback(runId),
          api.workflow().catch(() => undefined),
        ]);
      let result: ResultView | undefined;
      if (isExecutionTerminal(run.execution_status)) {
        try {
          result = await api.result(runId);
        } catch (reason) {
          if (!(
            reason instanceof ApiError &&
            ["result_unavailable", "run_not_finished"].includes(reason.code)
          ))
            throw reason;
        }
      }
      setState({
        run,
        events: history.items,
        result,
        sources: sources.items,
        steps,
        metrics,
        feedback,
        workflow,
        loading: false,
        error: workflow
          ? undefined
          : "Tên giai đoạn đang tạm gián đoạn. Kết quả và các bước xử lý vẫn hiển thị bằng mã giai đoạn.",
      });
      return { run, cursor: history.next_after };
    } catch (reason) {
      setState((current) => ({
        ...current,
        loading: false,
        error: reason instanceof Error ? reason.message : "Không tải được run.",
      }));
    }
  }, [api, apiSession, runId]);
  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    void (async () => {
      let snapshot = await refresh();
      if (!snapshot) return;
      let cursor = snapshot.cursor;
      while (!disposed && !isExecutionTerminal(snapshot.run.execution_status)) {
        try {
          await api.streamRunEvents(runId, {
            signal: controller.signal,
            after: cursor,
            onEvent: (event) => {
              if (event.sequence <= cursor) return;
              cursor = event.sequence;
              setState((current) => ({
                ...current,
                events: [
                  ...current.events.filter(
                    (item) => item.sequence !== event.sequence,
                  ),
                  event,
                ].sort((a, b) => a.sequence - b.sequence),
              }));
            },
          });
        } catch (reason) {
          if (controller.signal.aborted || disposed) return;
          if (reason instanceof ApiError && reason.code === "session_expired") {
            setState((current) => ({
              ...current,
              error:
                "Phiên đã hết hạn; stream đã dừng và không tạo phiên thay thế.",
            }));
            return;
          }
        }
        if (disposed) return;
        const next = await refresh();
        if (!next) return;
        snapshot = next;
        cursor = Math.max(cursor, next.cursor);
        if (!isExecutionTerminal(snapshot.run.execution_status)) {
          await new Promise((resolve) => window.setTimeout(resolve, 800));
        }
      }
    })();
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [api, refresh, runId]);
  return { state, refresh };
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ApiRunDetail({ runId }: { runId: string }) {
  const app = useApp();
  const gate = evaluateRunModelMode(app.capabilities, {
    allowLiveModelCalls: app.allowLiveModelCalls,
    liveModelConsent: app.liveModelConsent,
  });
  const navigate = useNavigate();
  const { state, refresh } = useApiRun(runId);
  const [assetImageUrl, setAssetImageUrl] = useState<string>();
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [actionError, setActionError] = useState("");
  const assetId = state.run?.asset_id;
  const mutationKeys = useRef(new Map<string, string>());
  const stableActionKey = (name: string) => {
    const existing = mutationKeys.current.get(name);
    if (existing) return existing;
    const created = createIdempotencyKey(name);
    mutationKeys.current.set(name, created);
    return created;
  };
  useEffect(() => {
    setNote(state.feedback?.note || "");
  }, [state.feedback?.note]);
  useEffect(() => {
    setAssetImageUrl(undefined);
    if (!assetId) return;
    let url: string | undefined;
    const controller = new AbortController();
    void app.api
      .assetContent(assetId, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        setAssetImageUrl(url);
      })
      .catch(() => {
        if (!controller.signal.aborted) setAssetImageUrl(undefined);
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [app.api, assetId]);
  const act = async (name: string, action: () => Promise<unknown>) => {
    setBusy(name);
    setActionError("");
    try {
      await action();
      await refresh();
    } catch (reason) {
      const error = reason instanceof ApiError ? reason : null;
      setActionError(
        `${reason instanceof Error ? reason.message : "Thao tác thất bại."}${error?.requestId ? ` · Request ID: ${error.requestId}` : ""}`,
      );
    } finally {
      setBusy("");
    }
  };
  if (!app.apiSession)
    return (
      <div className="page-shell">
        <EmptyState
          title="Phiên không còn trong bộ nhớ"
          icon={<Archive size={27} />}
        >
          Frontend không tự tạo phiên mới vì lịch sử này thuộc token cũ.{" "}
          <Link to="/login">Gắn lại token phù hợp</Link>.
        </EmptyState>
      </div>
    );
  if (state.loading)
    return (
      <div className="page-shell">
        <StatusCard kind="loading" title="Đang tải run và lịch sử sự kiện…" />
      </div>
    );
  if (state.error && !state.run)
    return (
      <div className="page-shell">
        <StatusCard kind="error" title="Không tải được run">
          {state.error}
        </StatusCard>
      </div>
    );
  const run = state.run!;
  const stages = Object.entries(state.steps?.items || {});
  const calls = state.metrics?.calls || [];
  const stageTitles = new Map(
    state.workflow?.stages.map((stage) => [stage.id, stage.title]),
  );
  return (
    <div className="run-page page-shell">
      <header className="run-header">
        <div className="run-title-with-image">
          {assetImageUrl ? (
            <ResilientImage
              src={assetImageUrl}
              alt="Ảnh đầu vào của run"
              className="run-input-image"
              loading="eager"
              retryable={false}
            />
          ) : (
            <span className="run-image-placeholder">
              <FileImage size={23} />
            </span>
          )}
          <div>
            <span className="eyebrow">
              RUN ·{" "}
              {run.run_kind === "review"
                ? "JUDGE-ONLY REVIEW"
                : "FULL WORKFLOW"}
            </span>
            <h1>{run.question}</h1>
            <div className="detail-badges">
              <Badge
                tone={
                  run.execution_status === "succeeded"
                    ? "green"
                    : run.execution_status === "failed"
                      ? "red"
                      : "blue"
                }
              >
                {executionLabels[run.execution_status]}
              </Badge>
              {(state.result?.status || run.result_status) && (
                <Badge
                  tone={
                    (state.result?.status || run.result_status) === "reviewed"
                      ? "green"
                      : "gold"
                  }
                >
                  {resultLabels[
                    state.result?.status || run.result_status || ""
                  ] ||
                    state.result?.status ||
                    run.result_status}
                </Badge>
              )}
              <Badge>{run.model_mode}</Badge>
            </div>
          </div>
        </div>
        <div className="run-header-actions">
          <Button
            tone="secondary"
            onClick={() =>
              act("bookmark", () => app.api.bookmarkRun(runId, !run.bookmarked))
            }
          >
            <BookHeart size={16} /> {run.bookmarked ? "Bỏ lưu run" : "Lưu run"}
          </Button>
          <Link className="button secondary" to="/chat">
            Câu hỏi mới
          </Link>
        </div>
      </header>
      {state.error && (
        <StatusCard kind="warning" title="Cập nhật chưa hoàn tất">
          {state.error}
        </StatusCard>
      )}
      {actionError && (
        <p className="form-alert" role="alert">
          {actionError}
        </p>
      )}
      <LiveModelConsent />
      {!gate.allowed && (
        <StatusCard kind="warning" title="Retry và review đang bị khóa">
          {gate.message}
        </StatusCard>
      )}
      {state.result?.reused_nodes.length ? (
        <StatusCard
          kind="info"
          title="Judge-only review đã tái sử dụng artifact"
        >
          Các stage được backend đánh dấu tái sử dụng:{" "}
          {state.result.reused_nodes.join(", ")}. Chỉ model attempt mới của run
          review xuất hiện trong metrics.
        </StatusCard>
      ) : null}
      <div className="run-action-bar">
        {!isExecutionTerminal(run.execution_status) && (
          <Button
            tone="danger"
            disabled={Boolean(busy)}
            onClick={() => act("cancel", () => app.api.cancelRun(runId))}
          >
            <CircleStop size={16} />{" "}
            {run.execution_status === "cancel_requested"
              ? "Đang yêu cầu hủy"
              : "Yêu cầu hủy"}
          </Button>
        )}
        {isExecutionTerminal(run.execution_status) && (
          <Button
            tone="secondary"
            disabled={Boolean(busy) || !gate.allowed}
            onClick={() =>
              act("retry", async () => {
                const next = await app.api.retryRun(
                  runId,
                  stableActionKey("retry"),
                );
                navigate(`/chat/runs/${next.run_id}`);
              })
            }
          >
            <RotateCcw size={16} /> Retry toàn bộ
          </Button>
        )}
        {isExecutionTerminal(run.execution_status) && (
          <Button
            tone="secondary"
            disabled={Boolean(busy) || !gate.allowed}
            onClick={() =>
              act("review", async () => {
                const next = await app.api.reviewRun(
                  runId,
                  stableActionKey("review"),
                );
                navigate(`/chat/runs/${next.run_id}`);
              })
            }
          >
            <SearchCheck size={16} /> Judge-only review
          </Button>
        )}
        {state.result && (
          <>
            <Button
              tone="ghost"
              onClick={() =>
                act("export-json", async () => {
                  const result = await app.api.exportRun(runId, {
                    format: "json",
                  });
                  downloadBlob(
                    result.blob,
                    result.filename || `heritage-${runId}.json`,
                  );
                })
              }
            >
              <Download size={16} /> JSON
            </Button>
            <Button
              tone="ghost"
              onClick={() =>
                act("export-md", async () => {
                  const result = await app.api.exportRun(runId, {
                    format: "markdown",
                  });
                  downloadBlob(
                    result.blob,
                    result.filename || `heritage-${runId}.md`,
                  );
                })
              }
            >
              <Download size={16} /> Markdown
            </Button>
          </>
        )}
        <button className="refresh-link" onClick={() => refresh()}>
          <RefreshCw size={14} /> Làm mới
        </button>
      </div>
      <div className="run-layout">
        <main className="answer-column">
          {state.result?.final_response ? (
            <section className="answer-card">
              <div className="answer-card-head">
                <span>
                  <Sparkles size={18} /> Câu trả lời cuối
                </span>
                <span>{state.result.duration.toFixed(2)} giây</span>
              </div>
              <Markdown>{state.result.final_response}</Markdown>
            </section>
          ) : (
            <StatusCard
              kind={
                isExecutionTerminal(run.execution_status)
                  ? "warning"
                  : "loading"
              }
              title={
                isExecutionTerminal(run.execution_status)
                  ? "Không có câu trả lời cuối khả dụng"
                  : "Workflow đang xử lý"
              }
            >
              {run.error_type
                ? `Lỗi: ${run.error_type}`
                : `Đã ghi nhận ${state.events.length} sự kiện.`}
            </StatusCard>
          )}
          <section className="sources-section">
            <div className="section-head">
              <div>
                <span className="eyebrow">CHỨNG CỨ ĐÃ TRUY XUẤT</span>
                <h2>Nguồn hỗ trợ</h2>
              </div>
              <Badge>{state.sources.length} nguồn</Badge>
            </div>
            {state.sources.length ? (
              <div className="source-cards">
                {state.sources.map((source) => (
                  <article
                    id={`source-${source.source_id}`}
                    key={source.source_id}
                  >
                    <span className="source-number">{source.number}</span>
                    <div>
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <strong>{source.title}</strong>
                      </a>
                      <p>{source.snippet}</p>
                      <small>
                        {source.type} ·{" "}
                        {source.cited
                          ? "được trích dẫn"
                          : "đã truy xuất, chưa trích dẫn"}
                      </small>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">
                Chưa có nguồn chứng cứ được API công khai.
              </p>
            )}
          </section>
          <section className="feedback-card feedback-form">
            <div>
              <strong>Đánh giá câu trả lời</strong>
              <p>
                Đây là feedback owner-scoped của run, không phải moderation.
              </p>
            </div>
            <textarea
              aria-label="Ghi chú phản hồi"
              maxLength={1500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Ghi chú tùy chọn…"
            />
            <div>
              <Button
                tone="secondary"
                disabled={Boolean(busy)}
                aria-pressed={state.feedback?.rating === "helpful"}
                onClick={() =>
                  act("feedback", () =>
                    app.api.setFeedback(runId, { rating: "helpful", note }),
                  )
                }
              >
                <ThumbsUp size={16} /> Hữu ích
              </Button>
              <Button
                tone="secondary"
                disabled={Boolean(busy)}
                aria-pressed={state.feedback?.rating === "needs_review"}
                onClick={() =>
                  act("feedback", () =>
                    app.api.setFeedback(runId, {
                      rating: "needs_review",
                      note,
                    }),
                  )
                }
              >
                <ThumbsDown size={16} /> Cần xem lại
              </Button>
            </div>
          </section>
        </main>
        <aside className="execution-column">
          <section className="panel execution-panel">
            <div className="section-head">
              <div>
                <span className="eyebrow">MỨC 1</span>
                <h2>Workflow stages</h2>
              </div>
              <Workflow size={20} />
            </div>
            {stages.length ? (
              <div className="stage-list">
                {stages.map(([id, raw]) => {
                  const stage = raw as Record<string, unknown>;
                  const payload = (stage.payload || {}) as Record<
                    string,
                    unknown
                  >;
                  return (
                    <details key={id}>
                      <summary>
                        <span
                          className={`status-dot ${String(stage.status || "waiting")}`}
                        />
                        <span>
                          <strong>{stageTitles.get(id) || id}</strong>
                          <small>{String(stage.status || "waiting")}</small>
                        </span>
                        <ChevronDown size={15} />
                      </summary>
                      <p>
                        {String(
                          payload.summary || "Không có tóm tắt công khai.",
                        )}
                      </p>
                      <pre>{JSON.stringify(stage, null, 2)}</pre>
                    </details>
                  );
                })}
              </div>
            ) : (
              <p className="muted">Chưa có snapshot giai đoạn.</p>
            )}
          </section>
          <section className="panel execution-panel">
            <div className="section-head">
              <div>
                <span className="eyebrow">MỨC 2</span>
                <h2>Model attempts</h2>
              </div>
              <Badge>{calls.length}</Badge>
            </div>
            {calls.length ? (
              <div className="call-list">
                {calls.map((raw, index) => {
                  const call = raw as Record<string, unknown>;
                  return (
                    <details
                      key={`${String(call.agent_role || "call")}-${String(call.attempt || index)}`}
                    >
                      <summary>
                        <span>
                          <strong>
                            {String(call.agent_role || "Model call")}
                          </strong>
                          <small>
                            {String(call.status || "unknown")} ·{" "}
                            {String(
                              call.actual_provider ||
                                "provider không công khai",
                            )}
                          </small>
                        </span>
                        <ChevronDown size={15} />
                      </summary>
                      <pre>{JSON.stringify(call, null, 2)}</pre>
                    </details>
                  );
                })}
              </div>
            ) : (
              <p className="muted">
                API chưa ghi nhận model attempt công khai.
              </p>
            )}
          </section>
          <section className="panel limitation-panel">
            <span className="eyebrow">MỨC 3</span>
            <h3>Tool / API calls</h3>
            <p>
              Backend hiện không có endpoint trace tool call hoặc input/output
              từng call. Frontend không tái dựng prompt hay hidden reasoning.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}

export function RunDetailPage() {
  const app = useApp();
  const { runId = "" } = useParams();
  return app.mode === "preview" ? (
    <PreviewRunDetail runId={runId} />
  ) : (
    <ApiRunDetail runId={runId} />
  );
}
