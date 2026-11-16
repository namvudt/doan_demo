import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../app/AppContext";
import { createIdempotencyKey, evaluateRunModelMode } from "../api/contracts";
import type { ClarificationView, ResultView } from "../api/schema";
import { Badge, Button, Field, StatusCard } from "./Ui";
import "./evidence-experience.css";

const recognitionLabels = {
  probable: "Có thể là",
  recognized: "Đã nhận diện",
  ambiguous: "Còn nhiều khả năng",
  unrecognized: "Chưa nhận diện được",
};
const verdictLabels = {
  supported: "Có bằng chứng hỗ trợ",
  contradicted: "Có bằng chứng mâu thuẫn",
  insufficient: "Chưa đủ bằng chứng",
  not_assessable: "Chưa thể đánh giá",
};

function RegionImage({ runId, regionId }: { runId: string; regionId: string }) {
  const { api } = useApp();
  const [imageUrl, setImageUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let url = "";
    void api
      .regionImage(runId, regionId, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        setImageUrl(url);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Không tải được vùng ảnh này.");
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [api, runId, regionId]);
  return imageUrl ? (
    <img
      className="evidence-region-image"
      src={imageUrl}
      alt="Vùng ảnh được dùng làm bằng chứng"
    />
  ) : (
    <p className="muted">{error || "Đang tải vùng ảnh…"}</p>
  );
}

export function EvidencePanel({ result }: { result: ResultView }) {
  const [registryOpen, setRegistryOpen] = useState(false);
  const recognition = result.recognition;
  const evidence = result.evidence || [];
  const claims = result.claims || [];
  const regions = result.regions || [];
  const qualityFlags = Array.isArray(result.image_quality?.flags)
    ? result.image_quality.flags.filter(
        (flag): flag is string => typeof flag === "string",
      )
    : [];
  if (
    (result.result_schema_version || 1) < 2 &&
    !recognition &&
    !evidence.length
  )
    return null;
  return (
    <section
      className="evidence-panel panel"
      aria-label="Nhận diện và bằng chứng"
    >
      <div className="section-head">
        <div>
          <span className="eyebrow">ĐỐI CHIẾU CÂU TRẢ LỜI</span>
          <h2>Nhận diện và bằng chứng</h2>
        </div>
        <Badge tone="gold">Đánh giá tự động</Badge>
      </div>
      {recognition && (
        <div className="recognition-result" data-testid="recognition-result">
          <strong>
            {recognitionLabels[recognition.status]}
            {recognition.name ? `: ${recognition.name}` : ""}
          </strong>
          <p>{recognition.explanation}</p>
          <small>
            {recognition.evidence_ids.length} bằng chứng ảnh hỗ trợ. Nhận diện
            không xác nhận mọi thông tin lịch sử.
          </small>
        </div>
      )}
      {result.location_hint && (
        <p className="muted">
          Gợi ý{" "}
          {result.location_hint.provenance === "sample_label"
            ? "từ nhãn ảnh mẫu"
            : "từ người dùng"}
          : {result.location_hint.name}. Đây không phải bằng chứng đã xác minh.
        </p>
      )}
      <p className="muted">
        Nguồn và nhận định được đối chiếu tự động; vẫn cần kiểm tra trước khi sử
        dụng như thông tin đã xác thực.
      </p>
      {Object.keys(result.image_quality || {}).length > 0 && (
        <details className="evidence-registry">
          <summary>Chất lượng ảnh</summary>
          <p>
            {qualityFlags.length
              ? qualityFlags
                  .map(
                    (flag) =>
                      ({
                        small_image: "Ảnh có độ phân giải thấp",
                        dark_image: "Ảnh tối",
                        low_contrast: "Độ tương phản thấp",
                      })[flag] || flag,
                  )
                  .join(" · ")
              : "Chưa ghi nhận cảnh báo chất lượng ảnh."}
          </p>
          <small>
            Các chỉ số chỉ là tín hiệu hỗ trợ, không bảo đảm đọc rõ mọi chi
            tiết.
          </small>
        </details>
      )}
      {claims.length > 0 && (
        <div className="evidence-claims" data-testid="evidence-claims">
          {claims.map((claim) => (
            <article key={claim.claim_id}>
              <Badge tone={claim.verdict === "supported" ? "green" : "gold"}>
                {verdictLabels[claim.verdict]}
              </Badge>
              <p>{claim.text}</p>
              {claim.explanation && <small>{claim.explanation}</small>}
              {claim.evidence_ids.length > 0 && (
                <div className="evidence-links">
                  {claim.evidence_ids
                    .filter((id) =>
                      evidence.some((item) => item.evidence_id === id),
                    )
                    .map((id) => (
                      <a
                        key={id}
                        href={`#evidence-${id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          setRegistryOpen(true);
                          requestAnimationFrame(() =>
                            document
                              .getElementById(`evidence-${id}`)
                              ?.scrollIntoView({ block: "nearest" }),
                          );
                        }}
                      >
                        Đối chiếu bằng chứng
                      </a>
                    ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      <details
        className="evidence-registry"
        open={registryOpen}
        onToggle={(event) => setRegistryOpen(event.currentTarget.open)}
      >
        <summary>Bằng chứng đã thu thập ({evidence.length})</summary>
        {evidence.map((item) => (
          <article id={`evidence-${item.evidence_id}`} key={item.evidence_id}>
            <Badge>
              {item.kind === "source"
                ? "Tư liệu"
                : item.kind === "ocr"
                  ? "Chữ trong ảnh"
                  : "Quan sát ảnh"}
            </Badge>
            <p>{item.text}</p>
            {item.source_id && (
              <a href={`#source-${item.source_id}`}>Xem nguồn hỗ trợ</a>
            )}
            {item.region_id && (
              <RegionDisclosure
                runId={result.run_id}
                regionId={item.region_id}
              />
            )}
          </article>
        ))}
        {!evidence.length && (
          <p className="muted">
            Chưa có bằng chứng được backend đăng ký cho câu trả lời này.
          </p>
        )}
      </details>
      {regions.length > 0 && (
        <details className="evidence-registry">
          <summary>Vùng ảnh đã xử lý ({regions.length})</summary>
          {regions.map(
            (region, index) =>
              typeof region.region_id === "string" && (
                <article key={region.region_id}>
                  <p>
                    {typeof region.purpose === "string"
                      ? region.purpose
                      : `Vùng ảnh ${index + 1}`}
                  </p>
                  <RegionDisclosure
                    runId={result.run_id}
                    regionId={region.region_id}
                  />
                </article>
              ),
          )}
        </details>
      )}
      {!!result.tool_calls?.length && (
        <details className="evidence-registry">
          <summary>Công cụ đã sử dụng ({result.tool_calls.length})</summary>
          <ul>
            {result.tool_calls.map((call, index) => (
              <li key={String(call.call_id || index)}>
                {String(call.tool || "Công cụ")} ·{" "}
                {String(call.status || "không rõ")}
                {typeof call.duration === "number"
                  ? ` · ${call.duration.toFixed(2)} giây`
                  : ""}
                {call.cached ? " · dùng lại kết quả" : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function RegionDisclosure({
  runId,
  regionId,
}: {
  runId: string;
  regionId: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Xem vùng ảnh</summary>
      {open && <RegionImage runId={runId} regionId={regionId} />}
    </details>
  );
}

export function ClarificationForm({
  runId,
  result,
}: {
  runId: string;
  result: ResultView;
}) {
  const app = useApp();
  const navigate = useNavigate();
  const [pending, setPending] = useState<ClarificationView>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState("");
  const [selected, setSelected] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const uploaded = useRef<{ file: File; assetId: string } | undefined>(
    undefined,
  );
  const keys = useRef(new Map<string, string>());
  const gate = evaluateRunModelMode(app.capabilities, {
    allowLiveModelCalls: app.allowLiveModelCalls,
    liveModelConsent: app.liveModelConsent,
  });
  useEffect(() => {
    const controller = new AbortController();
    void app.api
      .clarification(runId, controller.signal)
      .then((view) => {
        if (!controller.signal.aborted) setPending(view);
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Không tải được yêu cầu bổ sung.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [app.api, runId]);
  const clarification = pending?.clarification;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!clarification || !gate.allowed || busy) return;
    setBusy(true);
    setError("");
    try {
      // Re-check mode before an optional upload and before creating the child run.
      await app.api.ensureRunMode();
      let assetId: string | undefined;
      if (file) {
        if (uploaded.current?.file !== file)
          uploaded.current = {
            file,
            assetId: (await app.api.uploadAsset(file)).asset_id,
          };
        assetId = uploaded.current.assetId;
      }
      const body = {
        clarification_id: clarification.clarification_id,
        revision: clarification.revision,
        answer: answer.trim(),
        ...(selected ? { selected_candidate: selected } : {}),
        ...(assetId ? { asset_id: assetId } : {}),
      };
      const identity = JSON.stringify(body);
      const key =
        keys.current.get(identity) || createIdempotencyKey("clarification");
      keys.current.set(identity, key);
      const child = await app.api.submitClarification(runId, body, key);
      navigate(`/chat/runs/${child.run_id}`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Không gửi được thông tin bổ sung.",
      );
      // A concurrent continuation may already exist; read it without submitting again.
      void app.api
        .clarification(runId)
        .then(setPending)
        .catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className="clarification-panel panel"
      aria-label="Bổ sung thông tin"
      data-testid="clarification-panel"
    >
      <span className="eyebrow">CẦN BẠN BỔ SUNG</span>
      <h2>Bổ sung thông tin</h2>
      {loading ? (
        <StatusCard kind="loading" title="Đang tải câu hỏi bổ sung…" />
      ) : pending?.continuation_run_id ? (
        <p>
          Thông tin đã được gửi.{" "}
          <Link to={`/chat/runs/${pending.continuation_run_id}`}>
            Mở lượt trả lời tiếp theo
          </Link>
          .
        </p>
      ) : clarification ? (
        <form onSubmit={submit}>
          <p>{clarification.question}</p>
          {clarification.options.length > 0 && (
            <Field label="Địa điểm bạn muốn đối chiếu">
              <select
                aria-label="Địa điểm bạn muốn đối chiếu"
                value={selected}
                disabled={busy}
                onChange={(event) => setSelected(event.target.value)}
              >
                <option value="">Chưa chọn / chưa chắc chắn</option>
                {clarification.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Thông tin bổ sung">
            <textarea
              aria-label="Thông tin bổ sung"
              value={answer}
              maxLength={2000}
              disabled={busy}
              onChange={(event) => setAnswer(event.target.value)}
              placeholder="Chỉ bổ sung điều bạn biết; có thể để trống khi chọn ứng viên hoặc gửi ảnh."
            />
          </Field>
          <Field label="Ảnh bổ sung (tùy chọn)">
            <input
              aria-label="Ảnh bổ sung (tùy chọn)"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={busy}
              onChange={(event) => {
                setFile(event.target.files?.[0] || null);
                uploaded.current = undefined;
              }}
            />
          </Field>
          <small>
            Câu hỏi gốc được giữ nguyên. Thông tin bạn cung cấp được dùng làm
            gợi ý để đối chiếu.
          </small>
          {!gate.allowed && <p className="form-alert">{gate.message}</p>}
          <Button
            type="submit"
            disabled={
              busy || !gate.allowed || (!answer.trim() && !selected && !file)
            }
          >
            {busy ? "Đang gửi bổ sung…" : "Gửi thông tin bổ sung"}
          </Button>
        </form>
      ) : (
        <p>
          {result.answer_status === "needs_clarification"
            ? "Yêu cầu bổ sung không còn khả dụng. Hãy làm mới để xem trạng thái mới nhất."
            : "Không có câu hỏi bổ sung đang chờ."}
        </p>
      )}
      {error && (
        <p className="form-alert" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
