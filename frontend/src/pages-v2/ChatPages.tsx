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
  Landmark,
  MessageSquareText,
  RefreshCw,
  RotateCcw,
  SearchCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Workflow,
  X,
} from "lucide-react";
import {
  ApiError,
  createIdempotencyKey,
  evaluateRunModelMode,
  isExecutionTerminal,
  isExecutionSettled,
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
import { ChatComposer } from "../ui/ChatComposer";
import { ChatWorkspace } from "../ui/ChatWorkspace";
import { useHeritageRecord } from "../ui/useHeritageCatalog";
import type { Conversation, ConversationMessage } from "../api/product";
import { ClarificationForm, EvidencePanel } from "../ui/EvidencePanel";
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
  awaiting_input: "Chờ bạn bổ sung",
};
const resultLabels: Record<string, string> = {
  reviewed: "Đã được đánh giá tự động",
  unverified: "Chưa hoàn tất đánh giá",
  insufficient_evidence: "Chưa đủ bằng chứng",
  out_of_scope: "Ngoài phạm vi hỗ trợ",
  failed: "Kết quả gặp lỗi",
  answered: "Đã trả lời theo bằng chứng",
  partial: "Đã trả lời một phần",
  needs_clarification: "Cần bổ sung thông tin",
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
  const previewTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(previewTimer.current), []);
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
    if (!question.trim() || previewTimer.current !== undefined) return;
    setBusy(true);
    previewTimer.current = window.setTimeout(() => {
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
      previewTimer.current = undefined;
      setBusy(false);
      navigate(`/chat/runs/${run.id}`);
    }, 650);
  };
  const recentRuns = readPreviewRuns();
  return (
    <ChatWorkspace
      modeLabel="UI Preview"
      historyCount={recentRuns.length}
      history={
        recentRuns.length ? (
          <div className="history-list">
            {recentRuns.map((run) => (
              <Link to={`/chat/runs/${run.id}`} key={run.id}>
                <MessageSquareText size={17} />
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
            title="Chưa có câu hỏi"
            icon={<MessageSquareText size={26} />}
          >
            Những cuộc khám phá trong tab này sẽ xuất hiện ở đây.
          </EmptyState>
        )
      }
    >
      <header className="chat-welcome">
        <span className="chat-welcome-mark" aria-hidden="true">
          <Landmark size={30} />
        </span>
        <span className="eyebrow">BẮT ĐẦU TỪ ĐIỀU BẠN TÒ MÒ</span>
        <h1>Khám phá di sản cùng AI</h1>
        <p>
          Thêm ảnh, đặt câu hỏi và tìm hiểu câu chuyện phía sau những điều bạn
          nhìn thấy.
        </p>
      </header>
      <ChatComposer
        question={question}
        onQuestionChange={setQuestion}
        onSubmit={submit}
        questionLabel="Bạn muốn tìm hiểu điều gì?"
        placeholder="Ví dụ: Những chi tiết kiến trúc nào có thể quan sát trong ảnh?"
        imageUrl={previewUrl}
        imageName={
          file?.name ||
          (heritage ? `${heritage.name} · ảnh minh họa` : undefined)
        }
        imageHint="JPEG, PNG, WebP · tối đa 10 MB"
        onFileChange={setFile}
        onRemoveImage={file ? () => setFile(null) : undefined}
        busy={busy}
        submitLabel="Khám phá"
        busyLabel="Đang mô phỏng…"
        notice="UI Preview mô phỏng trải nghiệm, không gọi AI thật và không lưu lên máy chủ."
        context={
          heritage ? (
            <div className="context-chip">
              <Landmark size={16} />
              <span>
                <small>Đang khám phá</small>
                <strong>{heritage.name}</strong>
              </span>
              <Link to="/chat" aria-label="Bỏ ngữ cảnh">
                <X size={16} />
              </Link>
            </div>
          ) : undefined
        }
        suggestions={[
          "Mô tả chi tiết nhìn thấy trong ảnh",
          "Thông tin nào cần kiểm chứng thêm?",
          "Các nguồn nào đang hỗ trợ câu trả lời?",
        ]}
      />
      <p className="chat-grounding-note">
        <SearchCheck size={15} /> Luôn xem trạng thái đánh giá và nguồn trước
        khi sử dụng câu trả lời.
      </p>
    </ChatWorkspace>
  );
}

function ApiChat() {
  const app = useApp();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const heritageId = params.get("heritage") || "";
  const heritage = useHeritageRecord(heritageId || undefined);
  const [dismissedHeritage, setDismissedHeritage] = useState("");
  const [heritageImageLoading, setHeritageImageLoading] = useState(false);
  const [question, setQuestion] = useState("");
  const [locationHint, setLocationHint] = useState("");
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
  const selectedConversation = params.get("conversation") || "";
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationMessages, setConversationMessages] = useState<
    ConversationMessage[]
  >([]);
  const [conversationTitle, setConversationTitle] = useState("");
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [conversationBusy, setConversationBusy] = useState(false);
  const [conversationError, setConversationError] = useState("");
  const conversationSupported =
    app.capabilities?.features?.conversations === true;
  useEffect(() => {
    if (!app.apiSession || !conversationSupported) {
      setConversations([]);
      return;
    }
    const controller = new AbortController();
    void app.product
      .conversations(controller.signal)
      .then((page) => {
        if (!controller.signal.aborted) setConversations(page.items);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setConversationError(
            reason instanceof Error
              ? reason.message
              : "Không tải được hội thoại.",
          );
      });
    return () => controller.abort();
  }, [app.product, app.apiSession, conversationSupported]);
  useEffect(() => {
    setConversationMessages([]);
    if (!app.apiSession || !conversationSupported || !selectedConversation)
      return;
    const controller = new AbortController();
    setConversationError("");
    void app.product
      .messages(selectedConversation, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted) setConversationMessages(page.items);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setConversationError(
            reason instanceof Error
              ? reason.message
              : "Không tải được tin nhắn.",
          );
      });
    return () => controller.abort();
  }, [
    app.product,
    app.apiSession,
    conversationSupported,
    selectedConversation,
  ]);
  const chooseConversation = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set("conversation", id);
    else next.delete("conversation");
    setParams(next, { replace: true });
  };
  const createConversation = async () => {
    setConversationBusy(true);
    setConversationError("");
    try {
      const created = await app.product.createConversation(
        conversationTitle.trim() || "Hội thoại mới",
        memoryEnabled,
      );
      setConversations((current) => [created, ...current]);
      chooseConversation(created.conversation_id);
      setConversationTitle("");
      app.notify("Đã tạo hội thoại. Chưa gửi câu hỏi tới model.");
    } catch (reason) {
      setConversationError(
        reason instanceof Error ? reason.message : "Không tạo được hội thoại.",
      );
    } finally {
      setConversationBusy(false);
    }
  };
  const createIntent = useRef<{ fingerprint: string; key: string } | null>(
    null,
  );
  const gate = evaluateRunModelMode(app.capabilities, {
    allowLiveModelCalls: app.allowLiveModelCalls,
    liveModelConsent: app.liveModelConsent,
  });

  const historyGeneration = useRef(0);
  const loadRuns = useCallback(async () => {
    const generation = ++historyGeneration.current;
    if (!app.apiSession) return setRuns([]);
    try {
      const page = await app.api.runs({ limit: 12 });
      if (generation === historyGeneration.current) setRuns(page.items);
    } catch {
      /* surfaced by actions */
    }
  }, [app.api, app.apiSession]);
  useEffect(() => {
    void loadRuns();
    return () => {
      historyGeneration.current += 1;
    };
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

  const importCatalogImage =
    app.capabilities?.features?.heritage_asset_import === true;
  const heritageMedia = heritage.record?.media[0];
  const activeHeritage = Boolean(
    heritageId && dismissedHeritage !== heritageId && !selectedSample && !file,
  );
  useEffect(() => {
    if (
      !activeHeritage ||
      !importCatalogImage ||
      !heritageMedia ||
      !sessionId
    ) {
      setHeritageImageLoading(false);
      return;
    }
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setHeritageImageLoading(true);
    setAsset(null);
    setImageUrl(undefined);
    setError("");
    void (async () => {
      try {
        const selectedAsset = await app.api.useHeritageMedia(
          heritageId,
          heritageMedia.media_id,
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
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Không tải được ảnh di sản. Hãy chọn ảnh khác.",
          );
      } finally {
        if (!controller.signal.aborted) setHeritageImageLoading(false);
      }
    })();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [
    app.api,
    activeHeritage,
    importCatalogImage,
    heritageId,
    heritageMedia,
    sessionId,
  ]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!app.apiSession)
      return navigate("/login", {
        state: { from: `/chat${params.size ? `?${params}` : ""}` },
      });
    if (!gate.allowed) return setError(gate.message);
    if (!question.trim()) return setError("Hãy nhập câu hỏi.");
    if (sampleLoading || heritageImageLoading) return;
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
        conversation_id: conversationSupported ? selectedConversation : "",
        heritage_id:
          activeHeritage &&
          app.capabilities?.features?.content_editorial &&
          app.capabilities?.accuracy?.enabled
            ? heritageId
            : "",
        location_hint: app.capabilities?.accuracy?.enabled
          ? locationHint.trim()
          : "",
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
          ...(conversationSupported && selectedConversation
            ? { conversation_id: selectedConversation }
            : {}),
          ...(activeHeritage &&
          heritageId &&
          app.capabilities?.features?.content_editorial &&
          app.capabilities?.accuracy?.enabled
            ? { heritage_id: heritageId }
            : {}),
          ...(app.capabilities?.accuracy?.enabled && locationHint.trim()
            ? {
                location_hint: {
                  name: locationHint.trim(),
                  provenance: "user" as const,
                },
              }
            : {}),
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
          <Link
            to="/login"
            state={{ from: `/chat${params.size ? `?${params}` : ""}` }}
          >
            Truy cập phiên khách
          </Link>
          .
        </EmptyState>
      </div>
    );
  return (
    <ChatWorkspace
      modeLabel={
        app.capabilities?.model_mode === "live" ? "AI thật" : "Demo API"
      }
      historyCount={runs.length}
      onRefreshHistory={() => void loadRuns()}
      history={
        runs.length ? (
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
            title="Chưa có câu hỏi"
            icon={<MessageSquareText size={26} />}
          >
            Các câu hỏi thuộc phiên hiện tại sẽ xuất hiện ở đây.
          </EmptyState>
        )
      }
    >
      <header className="chat-welcome">
        <span className="chat-welcome-mark" aria-hidden="true">
          <Landmark size={30} />
        </span>
        <span className="eyebrow">BẮT ĐẦU TỪ ĐIỀU BẠN TÒ MÒ</span>
        <h1>Khám phá di sản cùng AI</h1>
        <p>
          Thêm ảnh của bạn hoặc chọn một ảnh mẫu. Đặt câu hỏi và theo dõi nguồn
          hỗ trợ cho câu trả lời.
        </p>
      </header>
      <div className="chat-notices">
        <LiveModelConsent />
        {!gate.allowed && (
          <StatusCard
            kind={
              gate.code === "LIVE_MODEL_CONSENT_REQUIRED" ? "warning" : "error"
            }
            title="Chưa thể gửi câu hỏi"
          >
            {gate.message}
          </StatusCard>
        )}
        {preflight && (
          <StatusCard
            kind={preflight.ready ? "success" : "warning"}
            title={
              preflight.ready
                ? "Hệ thống sẵn sàng"
                : "Hệ thống cần được kiểm tra"
            }
          >
            <p>
              {preflight.ready
                ? "Các thành phần xử lý đã sẵn sàng. Kiểm tra này chưa xác nhận quota cho tác vụ AI."
                : "Một số thành phần xử lý chưa sẵn sàng. Hãy kiểm tra lại trước khi gửi."}
            </p>
            <details className="chat-readiness-details">
              <summary>Thông tin kết nối</summary>
              {preflight.roles
                .map(
                  (role) =>
                    `${role.role}: ${role.ready ? "ready" : role.error_code || "not ready"}`,
                )
                .join(" · ")}
            </details>
          </StatusCard>
        )}
        {heritageId && activeHeritage && (
          <StatusCard
            kind={heritage.loading || heritageImageLoading ? "loading" : "info"}
            title={
              heritageImageLoading
                ? "Đang chuẩn bị ảnh di sản…"
                : asset && importCatalogImage
                  ? "Đã chọn ảnh từ hồ sơ di sản"
                  : "Chọn ảnh cho câu hỏi này"
            }
          >
            {heritage.error ||
              (asset && importCatalogImage
                ? `Ảnh ${heritage.record?.name || "di sản"} đã được gắn vào phiên của bạn. Hãy nhập câu hỏi để bắt đầu. Nguồn metadata trong hồ sơ chưa được dùng làm bằng chứng RAG.`
                : "Hãy chọn hoặc tải ảnh và viết đầy đủ nội dung bạn muốn hỏi.")}
          </StatusCard>
        )}
      </div>
      <ChatComposer
        question={question}
        onQuestionChange={setQuestion}
        onSubmit={submit}
        questionLabel="Câu hỏi"
        maxLength={app.capabilities?.max_question_characters || 4000}
        imageUrl={imageUrl}
        imageName={
          file?.name ||
          app.apiSamples.find((sample) => sample.sample_id === selectedSample)
            ?.title ||
          (activeHeritage && asset ? heritage.record?.name : undefined) ||
          (asset ? "Ảnh đã sẵn sàng" : undefined)
        }
        imageAlt="Ảnh tải lên"
        imageBusy={sampleLoading || heritageImageLoading}
        imageHint={`JPEG, PNG, WebP · tối đa ${app.capabilities ? Math.round(app.capabilities.max_upload_bytes / 1_048_576) : "?"} MB`}
        maxUploadBytes={app.capabilities?.max_upload_bytes}
        context={
          <>
            {conversationSupported && (
              <details className="chat-readiness-details">
                <summary>Hội thoại và ngữ cảnh (tùy chọn)</summary>
                <Field label="Hội thoại đang dùng">
                  <select
                    value={selectedConversation}
                    disabled={loading || conversationBusy}
                    onChange={(event) => chooseConversation(event.target.value)}
                  >
                    <option value="">Câu hỏi độc lập</option>
                    {conversations.map((chat) => (
                      <option
                        key={chat.conversation_id}
                        value={chat.conversation_id}
                        disabled={chat.archived}
                      >
                        {chat.title}
                        {chat.memory_enabled ? " · có ngữ cảnh" : ""}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Tên hội thoại mới">
                  <input
                    value={conversationTitle}
                    maxLength={160}
                    onChange={(event) =>
                      setConversationTitle(event.target.value)
                    }
                    disabled={conversationBusy}
                    placeholder="Đặt tên để dễ tìm lại"
                  />
                </Field>
                <label className="checkbox-row conversation-memory-option">
                  <input
                    type="checkbox"
                    checked={memoryEnabled}
                    onChange={(event) => setMemoryEnabled(event.target.checked)}
                    disabled={conversationBusy}
                  />{" "}
                  Cho hội thoại mới dùng ngữ cảnh có giới hạn
                </label>
                <p className="small muted">
                  Ngữ cảnh tối đa 8 tin nhắn và 4.000 ký tự; lời người dùng và
                  đáp án trước vẫn cần kiểm chứng.
                </p>
                <Button
                  type="button"
                  tone="secondary"
                  disabled={loading || conversationBusy}
                  onClick={() => void createConversation()}
                >
                  Tạo hội thoại
                </Button>
                {selectedConversation && (
                  <>
                    <Button
                      type="button"
                      tone="ghost"
                      onClick={() =>
                        void app.product
                          .clearMemory(selectedConversation)
                          .then(() =>
                            app.notify(
                              "Các lượt tiếp theo không dùng ngữ cảnh cũ.",
                            ),
                          )
                          .catch((reason: unknown) =>
                            setConversationError(
                              reason instanceof Error
                                ? reason.message
                                : "Không xóa được ngữ cảnh.",
                            ),
                          )
                      }
                    >
                      Quên ngữ cảnh cũ
                    </Button>
                    <details>
                      <summary>
                        Lịch sử hội thoại ({conversationMessages.length})
                      </summary>
                      {conversationMessages.map((message) => (
                        <article key={message.message_id}>
                          <strong>
                            {message.role === "user" ? "Bạn" : "Trợ lý"}
                          </strong>
                          <p>{message.content.slice(0, 700)}</p>
                          <Link to={`/chat/runs/${message.run_id}`}>
                            Xem lượt xử lý
                          </Link>
                        </article>
                      ))}
                    </details>
                  </>
                )}
                {conversationError && (
                  <p className="form-alert" role="alert">
                    {conversationError}
                  </p>
                )}
              </details>
            )}
            {app.capabilities?.accuracy?.enabled ? (
              <details className="chat-readiness-details">
                <summary>Gợi ý địa điểm (tùy chọn)</summary>
                <Field label="Địa điểm bạn nghĩ tới">
                  <input
                    aria-label="Địa điểm bạn nghĩ tới"
                    maxLength={200}
                    value={locationHint}
                    disabled={loading}
                    onChange={(event) => setLocationHint(event.target.value)}
                    placeholder="Có thể để trống để nhận diện từ ảnh"
                  />
                </Field>
                <small>
                  Được gửi như gợi ý từ bạn, không phải đáp án hoặc bằng chứng
                  đã xác minh.
                </small>
              </details>
            ) : null}
          </>
        }
        onFileChange={(nextFile) => {
          setDismissedHeritage(heritageId);
          setFile(nextFile);
          setAsset(null);
          setSelectedSample("");
          setImageUrl(undefined);
          setError("");
        }}
        onRemoveImage={() => {
          setDismissedHeritage(heritageId);
          setFile(null);
          setSelectedSample("");
          setAsset(null);
          setImageUrl(undefined);
          setError("");
        }}
        sourceControl={
          <Field label="Ảnh mẫu từ hệ thống">
            <select
              value={selectedSample}
              disabled={loading}
              onChange={(event) => {
                setDismissedHeritage(heritageId);
                setSelectedSample(event.target.value);
                setFile(null);
                setAsset(null);
                setImageUrl(undefined);
                setError("");
              }}
            >
              <option value="">Chọn ảnh mẫu…</option>
              {app.apiSamples.map((sample) => (
                <option value={sample.sample_id} key={sample.sample_id}>
                  {sample.title}
                </option>
              ))}
            </select>
          </Field>
        }
        audience={{ value: audience, onChange: setAudience }}
        error={error}
        busy={loading}
        disabled={
          sampleLoading ||
          heritageImageLoading ||
          !gate.allowed ||
          (!asset && !file && !selectedSample)
        }
        submitLabel="Gửi câu hỏi"
        busyLabel="Đang gửi…"
        notice={
          app.capabilities?.model_mode === "live"
            ? "Ảnh và câu hỏi được gửi tới AI theo cấu hình hệ thống; mỗi tác vụ có thể phát sinh chi phí."
            : "Chế độ demo trả kết quả mô phỏng; ảnh và câu hỏi được gửi tới máy chủ."
        }
        auxiliaryAction={
          <Button
            type="button"
            tone="secondary"
            onClick={checkReadiness}
            disabled={checking || loading}
          >
            {checking ? "Đang kiểm tra…" : "Kiểm tra sẵn sàng"}
          </Button>
        }
        suggestions={[
          "Những chi tiết kiến trúc nào có thể quan sát trong ảnh?",
          "Thông tin nào về địa điểm này cần kiểm chứng thêm?",
          "Hãy giải thích ngắn gọn cho người lần đầu tìm hiểu.",
        ]}
      />
      <p className="chat-grounding-note">
        <SearchCheck size={15} /> Đối chiếu mức độ kiểm chứng và nguồn hỗ trợ
        trước khi sử dụng câu trả lời.
      </p>
    </ChatWorkspace>
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
  const linkedHeritage = preview.heritages.find(
    (item) => item.id === run.heritageId,
  );
  const linkedSources = preview.contentSources.filter((source) =>
    linkedHeritage?.sourceIds.includes(source.id),
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
    <div className="run-page page-shell chat-result-page">
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
      <div className="run-context-strip">
        <span>
          <FileImage size={15} /> {run.imageName || "Câu hỏi không kèm ảnh"}
        </span>
        <span>{new Date(run.createdAt).toLocaleString("vi-VN")}</span>
      </div>
      <div className="run-layout">
        <section
          className="answer-column"
          aria-label="Câu trả lời và nguồn hỗ trợ"
        >
          <section className="answer-card">
            <div className="answer-card-head">
              <span>
                <Sparkles size={18} /> Câu trả lời
              </span>
              <Badge tone="gold">Mô phỏng</Badge>
            </div>
            <Markdown>{run.answer}</Markdown>
          </section>
          <section className="sources-section">
            <div className="section-head">
              <div>
                <span className="eyebrow">TƯ LIỆU MINH HỌA</span>
                <h2>Nguồn hỗ trợ</h2>
              </div>
              <Badge>{linkedSources.length} nguồn</Badge>
            </div>
            {linkedSources.length ? (
              <div className="source-cards">
                {linkedSources.map((source, index) => (
                  <article key={source.id}>
                    <span className="source-number">{index + 1}</span>
                    <div>
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <strong>{source.title}</strong>
                      </a>
                      <p>{source.summary}</p>
                      <small>
                        {source.publisher} · Metadata hồ sơ Preview, chưa phải
                        kết quả truy xuất AI
                      </small>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">
                Chưa có tư liệu minh họa liên kết. Kết quả này chưa đủ nguồn để
                đối chiếu.
              </p>
            )}
          </section>
          <section className="feedback-card">
            <div>
              <strong>Kết quả mô phỏng này có rõ ràng không?</strong>
              <p>Phản hồi được lưu trong bản Preview của phiên này.</p>
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
        </section>
        <details className="execution-details">
          <summary>
            <span>
              <Workflow size={18} /> Chi tiết xử lý
            </span>
            <span className="execution-summary-hint">
              Các bước và trạng thái
            </span>
            <ChevronDown size={17} />
          </summary>
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
        </details>
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
      if (isExecutionSettled(run.execution_status)) {
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
      while (!disposed && !isExecutionSettled(snapshot.run.execution_status)) {
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
        if (!isExecutionSettled(snapshot.run.execution_status)) {
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
    <div className="run-page page-shell chat-result-page">
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
                : run.run_kind === "clarification"
                  ? "BỔ SUNG THÔNG TIN"
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
        <StatusCard kind="warning" title="Tác vụ AI mới đang bị khóa">
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
        {!isExecutionSettled(run.execution_status) && (
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
        <section
          className="answer-column"
          aria-label="Câu trả lời và nguồn hỗ trợ"
        >
          {state.result?.final_response ? (
            <section className="answer-card">
              <div className="answer-card-head">
                <span>
                  <Sparkles size={18} />{" "}
                  {run.execution_status === "awaiting_input"
                    ? "Phần trả lời hiện có"
                    : "Câu trả lời cuối"}
                </span>
                <span>{state.result.duration.toFixed(2)} giây</span>
              </div>
              <Markdown>{state.result.final_response}</Markdown>
            </section>
          ) : (
            <StatusCard
              kind={
                isExecutionSettled(run.execution_status) ? "warning" : "loading"
              }
              title={
                isExecutionSettled(run.execution_status)
                  ? run.execution_status === "awaiting_input"
                    ? "Cần bạn bổ sung để tiếp tục"
                    : "Không có câu trả lời cuối khả dụng"
                  : "Workflow đang xử lý"
              }
            >
              {run.error_type
                ? `Lỗi: ${run.error_type}`
                : `Đã ghi nhận ${state.events.length} sự kiện.`}
            </StatusCard>
          )}
          {state.result && run.execution_status === "awaiting_input" && (
            <ClarificationForm
              key={runId}
              runId={runId}
              result={state.result}
            />
          )}
          {state.result && <EvidencePanel result={state.result} />}
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
              <p className="muted">Chưa có nguồn hỗ trợ để đối chiếu.</p>
            )}
          </section>
          <section className="feedback-card feedback-form">
            <div>
              <strong>Đánh giá câu trả lời</strong>
              <p>Đánh dấu thông tin hữu ích hoặc cần kiểm tra lại.</p>
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
        </section>
        <details className="execution-details">
          <summary>
            <span>
              <Workflow size={18} /> Chi tiết xử lý
            </span>
            <span className="execution-summary-hint">
              Các bước và trạng thái
            </span>
            <ChevronDown size={17} />
          </summary>
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
                {state.result?.tool_calls?.length
                  ? `${state.result.tool_calls.length} lần dùng công cụ được backend ghi nhận; xem phần Nhận diện và bằng chứng.`
                  : "Chưa có lần dùng công cụ được backend ghi nhận cho lượt này."}{" "}
                Frontend không tái dựng prompt hay hidden reasoning.
              </p>
            </section>
          </aside>
        </details>
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
    <ApiRunDetail key={runId} runId={runId} />
  );
}
