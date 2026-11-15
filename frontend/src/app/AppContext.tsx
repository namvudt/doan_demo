import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { HttpApi } from "../api/http";
import type { BackendApi } from "../api/contracts";
import type {
  CapabilitiesView,
  RunView,
  SampleView,
  SessionView,
} from "../api/schema";
import { usePreview } from "../preview/PreviewProvider";

export type FrontendMode = "preview" | "api";
type Toast = { id: number; text: string; kind: "success" | "error" };

type AppContextValue = {
  mode: FrontendMode;
  switchMode(mode: FrontendMode): void;
  api: BackendApi;
  allowLiveModelCalls: boolean;
  liveModelConsent: boolean;
  setLiveModelConsent(consented: boolean): void;
  apiSession: SessionView | null;
  capabilities: CapabilitiesView | null;
  capabilitiesError: string;
  refreshCapabilities(): Promise<void>;
  createGuestSession(label: string): Promise<void>;
  attachGuestToken(token: string): Promise<void>;
  logoutApiSession(): Promise<void>;
  apiSamples: SampleView[];
  apiSamplesLoading: boolean;
  apiSamplesError: string;
  refreshApiSamples(): Promise<void>;
  savedRuns: RunView[];
  savedRunsLoading: boolean;
  savedRunsError: string;
  refreshSavedRuns(): Promise<void>;
  notify(text: string, kind?: "success" | "error"): void;
};

const AppContext = createContext<AppContextValue | null>(null);
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("AppProvider is missing");
  return value;
}

function messageOf(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const preview = usePreview();
  const defaultMode: FrontendMode =
    import.meta.env.VITE_FRONTEND_MODE === "api" ? "api" : "preview";
  const [mode, setMode] = useState<FrontendMode>(defaultMode);
  const allowLiveModelCalls =
    import.meta.env.VITE_ALLOW_LIVE_MODEL_CALLS === "true";
  const [liveModelConsent, setLiveConsentState] = useState(false);
  const api = useMemo(
    () =>
      new HttpApi({
        baseUrl: import.meta.env.VITE_API_BASE_URL || "/api/v1",
        timeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS) || 30_000,
        allowLiveModelCalls,
      }),
    [allowLiveModelCalls],
  );
  const setLiveModelConsent = useCallback(
    (consented: boolean) => {
      const allowed = allowLiveModelCalls && consented;
      api.setLiveModelConsent(allowed);
      setLiveConsentState(allowed);
    },
    [allowLiveModelCalls, api],
  );
  const [apiSession, setApiSession] = useState<SessionView | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesView | null>(
    null,
  );
  const [capabilitiesError, setCapabilitiesError] = useState("");
  const [apiSamples, setApiSamples] = useState<SampleView[]>([]);
  const [apiSamplesLoading, setApiSamplesLoading] = useState(false);
  const [apiSamplesError, setApiSamplesError] = useState("");
  const [savedRuns, setSavedRuns] = useState<RunView[]>([]);
  const [savedRunsLoading, setSavedRunsLoading] = useState(false);
  const [savedRunsError, setSavedRunsError] = useState("");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextToast = useRef(1);

  const notify = useCallback(
    (text: string, kind: "success" | "error" = "success") => {
      const id = nextToast.current++;
      setToasts((current) => [...current, { id, text, kind }].slice(-3));
      window.setTimeout(
        () => setToasts((current) => current.filter((item) => item.id !== id)),
        5_500,
      );
    },
    [],
  );

  const refreshCapabilities = useCallback(async () => {
    setCapabilitiesError("");
    try {
      setCapabilities(await api.capabilities());
    } catch (reason) {
      setCapabilities(null);
      setCapabilitiesError(
        messageOf(reason, "Không xác minh được capability của backend."),
      );
    }
  }, [api]);

  const refreshApiSamples = useCallback(async () => {
    if (mode !== "api") return;
    setApiSamplesLoading(true);
    setApiSamplesError("");
    try {
      setApiSamples((await api.samples()).items);
    } catch (reason) {
      setApiSamples([]);
      setApiSamplesError(
        messageOf(reason, "Không tải được sample từ backend."),
      );
    } finally {
      setApiSamplesLoading(false);
    }
  }, [api, mode]);

  const refreshSavedRuns = useCallback(async () => {
    if (mode !== "api" || !apiSession) {
      setSavedRuns([]);
      return;
    }
    setSavedRunsLoading(true);
    setSavedRunsError("");
    try {
      setSavedRuns((await api.runs({ saved_only: true, limit: 100 })).items);
    } catch (reason) {
      setSavedRuns([]);
      setSavedRunsError(messageOf(reason, "Không tải được run đã đánh dấu."));
    } finally {
      setSavedRunsLoading(false);
    }
  }, [api, apiSession, mode]);

  useEffect(() => {
    if (mode !== "api") return;
    void refreshCapabilities();
    void refreshApiSamples();
  }, [mode, refreshApiSamples, refreshCapabilities]);
  useEffect(() => {
    void refreshSavedRuns();
  }, [refreshSavedRuns]);

  const attachGuestToken = useCallback(
    async (token: string) => {
      setLiveModelConsent(false);
      api.setAccessToken(token);
      try {
        const session = await api.currentSession();
        setApiSession(session);
        notify("Đã gắn phiên khách vào bộ nhớ tab.");
      } catch (reason) {
        api.setAccessToken(undefined);
        setApiSession(null);
        throw reason;
      }
    },
    [api, notify, setLiveModelConsent],
  );

  const createGuestSession = useCallback(
    async (label: string) => {
      setLiveModelConsent(false);
      const currentCapabilities = capabilities || (await api.capabilities());
      setCapabilities(currentCapabilities);
      if (currentCapabilities.session_bootstrap_required) {
        throw new Error(
          "Backend yêu cầu bootstrap; trình duyệt chỉ được dùng guest access token do operator cấp.",
        );
      }
      const created = await api.createSession({ label });
      api.setAccessToken(created.access_token);
      try {
        setApiSession(await api.currentSession());
        notify("Đã tạo phiên khách mới. Token chỉ được giữ trong bộ nhớ tab.");
      } catch (reason) {
        api.setAccessToken(undefined);
        throw reason;
      }
    },
    [api, capabilities, notify, setLiveModelConsent],
  );

  const logoutApiSession = useCallback(async () => {
    let error: unknown;
    try {
      if (apiSession) await api.revokeCurrentSession();
    } catch (reason) {
      error = reason;
    } finally {
      setLiveModelConsent(false);
      api.setAccessToken(undefined);
      setApiSession(null);
      setSavedRuns([]);
    }
    if (error) throw error;
    notify("Đã thu hồi phiên khách và xóa token khỏi bộ nhớ tab.");
  }, [api, apiSession, notify, setLiveModelConsent]);

  const switchMode = useCallback(
    (next: FrontendMode) => {
      if (next === mode) return;
      setLiveModelConsent(false);
      api.setAccessToken(undefined);
      setApiSession(null);
      setSavedRuns([]);
      setCapabilities(null);
      setCapabilitiesError("");
      setApiSamples([]);
      if (next === "api") {
        preview.logout();
        sessionStorage.removeItem("heritage.ui-preview.runs.v1");
      }
      setMode(next);
    },
    [api, mode, preview, setLiveModelConsent],
  );

  const value: AppContextValue = {
    mode,
    switchMode,
    api,
    allowLiveModelCalls,
    liveModelConsent,
    setLiveModelConsent,
    apiSession,
    capabilities,
    capabilitiesError,
    refreshCapabilities,
    createGuestSession,
    attachGuestToken,
    logoutApiSession,
    apiSamples,
    apiSamplesLoading,
    apiSamplesError,
    refreshApiSamples,
    savedRuns,
    savedRunsLoading,
    savedRunsError,
    refreshSavedRuns,
    notify,
  };
  return (
    <AppContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <div
            className={`toast ${toast.kind}`}
            role={toast.kind === "error" ? "alert" : "status"}
            key={toast.id}
          >
            {toast.kind === "error" ? (
              <XCircle size={18} />
            ) : (
              <CheckCircle2 size={18} />
            )}
            <span>{toast.text}</span>
            <button
              aria-label="Đóng thông báo"
              onClick={() =>
                setToasts((current) =>
                  current.filter((item) => item.id !== toast.id),
                )
              }
            >
              <X size={15} />
            </button>
          </div>
        ))}
      </div>
    </AppContext.Provider>
  );
}
