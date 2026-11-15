import { useCallback, useEffect, useRef, useState } from "react";
import { Check, LoaderCircle, RefreshCw, Server, WifiOff } from "lucide-react";
import { useApp } from "../app/AppContext";
import "./backend-connection.css";

type Connection = {
  state: "checking" | "ready" | "limited" | "offline";
  mode?: string;
  database?: boolean;
  worker?: boolean;
  checkedAt?: Date;
};

export function BackendConnection() {
  const { api } = useApp();
  const [connection, setConnection] = useState<Connection>({
    state: "checking",
  });
  const activeCheck = useRef<AbortController | null>(null);
  const check = useCallback(async () => {
    activeCheck.current?.abort();
    const controller = new AbortController();
    activeCheck.current = controller;
    setConnection({ state: "checking" });
    try {
      const [capabilities, health] = await Promise.all([
        api.capabilities(controller.signal),
        api.ready(controller.signal),
      ]);
      if (controller.signal.aborted) return;
      setConnection({
        state:
          health.database &&
          health.worker &&
          (capabilities.model_mode === "demo" ||
            (capabilities.model_configured &&
              capabilities.missing_roles.length === 0))
            ? "ready"
            : "limited",
        mode: capabilities.model_mode,
        database: health.database,
        worker: health.worker,
        checkedAt: new Date(),
      });
    } catch {
      if (!controller.signal.aborted) {
        setConnection({ state: "offline", checkedAt: new Date() });
      }
    }
  }, [api]);

  useEffect(() => {
    void check();
    return () => activeCheck.current?.abort();
  }, [check]);

  const checking = connection.state === "checking";
  const ready = connection.state === "ready";
  const Icon = checking ? LoaderCircle : ready ? Server : WifiOff;
  return (
    <section
      className={`backend-connect ${connection.state}`}
      aria-label="Kết nối backend"
    >
      <div className="backend-connect-heading">
        <span className="backend-connect-icon">
          <Icon size={21} className={checking ? "spin" : ""} />
        </span>
        <div role="status" aria-live="polite">
          <strong>
            {checking
              ? "Đang kiểm tra kết nối…"
              : ready
                ? "Backend local đã sẵn sàng"
                : connection.state === "limited"
                  ? "Backend đang khởi động hoặc cần cấu hình"
                  : "Chưa kết nối được backend local"}
          </strong>
          <p>
            {ready
              ? connection.mode === "live"
                ? "API, cơ sở dữ liệu và worker đều phản hồi. AI thật đã được cấu hình; tác vụ có thể tính phí."
                : "API, cơ sở dữ liệu và worker đều phản hồi. AI đang dùng dữ liệu demo."
              : checking
                ? "Kiểm tra API và dịch vụ xử lý, thường chỉ mất vài giây."
                : connection.state === "limited"
                  ? "Bạn vẫn có thể khám phá Preview trong lúc dịch vụ chuẩn bị."
                  : "Khởi động Docker local rồi thử lại. Preview vẫn hoạt động bình thường."}
          </p>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label="Kiểm tra lại kết nối backend"
          onClick={check}
          disabled={checking}
        >
          <RefreshCw size={17} className={checking ? "spin" : ""} />
        </button>
      </div>
      {connection.database !== undefined && (
        <div className="backend-service-list">
          <span>
            <Check size={13} /> API
          </span>
          <span className={connection.database ? "" : "pending"}>
            {connection.database ? <Check size={13} /> : "○"} Dữ liệu
          </span>
          <span className={connection.worker ? "" : "pending"}>
            {connection.worker ? <Check size={13} /> : "○"} Xử lý
          </span>
        </div>
      )}
      <div className="backend-connect-foot">
        <span>
          {connection.mode
            ? `Chế độ: ${connection.mode}`
            : "Chỉ kiểm tra kết nối, không tạo tác vụ AI"}
        </span>
        {connection.checkedAt && (
          <time dateTime={connection.checkedAt.toISOString()}>
            {connection.checkedAt.toLocaleTimeString("vi-VN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </time>
        )}
      </div>
    </section>
  );
}
