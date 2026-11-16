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
import {
  ProductApi,
  type Account,
  type AccountAuth,
  type HeritageFavorite,
} from "../api/product";
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
  product: ProductApi;
  account: Account | null;
  loginAccount(email: string, password: string): Promise<void>;
  registerAccount(name: string, email: string, password: string): Promise<void>;
  refreshAccountSession(): Promise<void>;
  updateAccountName(name: string): Promise<void>;
  heritageFavorites: HeritageFavorite[];
  heritageFavoritesLoading: boolean;
  heritageFavoritesError: string;
  refreshHeritageFavorites(): Promise<void>;
  setHeritageFavorite(id: string, saved: boolean): Promise<void>;
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
  const product = useMemo(
    () => new ProductApi(import.meta.env.VITE_API_BASE_URL || "/api/v1"),
    [],
  );
  const [account, setAccount] = useState<Account | null>(null);
  const [heritageFavorites, setHeritageFavorites] = useState<
    HeritageFavorite[]
  >([]);
  const [heritageFavoritesLoading, setHeritageFavoritesLoading] =
    useState(false);
  const [heritageFavoritesError, setHeritageFavoritesError] = useState("");
  const refreshToken = useRef<string | undefined>(undefined);
  const identityEpoch = useRef(0);
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
    const epoch = identityEpoch.current;
    try {
      const page = await api.runs({ saved_only: true, limit: 100 });
      if (epoch === identityEpoch.current) setSavedRuns(page.items);
    } catch (reason) {
      if (epoch === identityEpoch.current) {
        setSavedRuns([]);
        setSavedRunsError(messageOf(reason, "Không tải được run đã đánh dấu."));
      }
    } finally {
      if (epoch === identityEpoch.current) setSavedRunsLoading(false);
    }
  }, [api, apiSession, mode]);

  const accountId = account?.account_id;
  const refreshHeritageFavorites = useCallback(async () => {
    if (mode !== "api" || !accountId) {
      setHeritageFavorites([]);
      return;
    }
    setHeritageFavoritesLoading(true);
    setHeritageFavoritesError("");
    const epoch = identityEpoch.current;
    try {
      const page = await product.favorites();
      if (epoch === identityEpoch.current) setHeritageFavorites(page.items);
    } catch (reason) {
      if (epoch === identityEpoch.current)
        setHeritageFavoritesError(
          messageOf(reason, "Không tải được di sản yêu thích."),
        );
    } finally {
      if (epoch === identityEpoch.current) setHeritageFavoritesLoading(false);
    }
  }, [accountId, mode, product]);
  useEffect(() => {
    void refreshHeritageFavorites();
  }, [refreshHeritageFavorites]);
  const setHeritageFavorite = useCallback(
    async (id: string, saved: boolean) => {
      if (!accountId) throw new Error("Hãy đăng nhập tài khoản để lưu di sản.");
      const epoch = identityEpoch.current;
      const result = await product.favorite(id, saved);
      if (epoch !== identityEpoch.current) return;
      setHeritageFavorites((current) =>
        result
          ? [result, ...current.filter((item) => item.heritage_id !== id)]
          : current.filter((item) => item.heritage_id !== id),
      );
    },
    [accountId, product],
  );

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
      identityEpoch.current += 1;
      setLiveModelConsent(false);
      api.setAccessToken(token);
      product.setAccessToken(token);
      refreshToken.current = undefined;
      setAccount(null);
      setHeritageFavorites([]);
      try {
        const session = await api.currentSession();
        setApiSession(session);
        if (capabilities?.features?.accounts) {
          const current = await product.me().catch(() => null);
          setAccount(current);
        }
        notify("Đã gắn phiên khách vào bộ nhớ tab.");
      } catch (reason) {
        api.setAccessToken(undefined);
        product.setAccessToken(undefined);
        setApiSession(null);
        throw reason;
      }
    },
    [api, product, capabilities, notify, setLiveModelConsent],
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
      identityEpoch.current += 1;
      api.setAccessToken(created.access_token);
      product.setAccessToken(created.access_token);
      refreshToken.current = undefined;
      setAccount(null);
      try {
        setApiSession(await api.currentSession());
        notify("Đã tạo phiên khách mới. Token chỉ được giữ trong bộ nhớ tab.");
      } catch (reason) {
        api.setAccessToken(undefined);
        product.setAccessToken(undefined);
        throw reason;
      }
    },
    [api, product, capabilities, notify, setLiveModelConsent],
  );

  const applyAccountSession = useCallback(
    async (issued: AccountAuth) => {
      identityEpoch.current += 1;
      setHeritageFavorites([]);
      setSavedRuns([]);
      setLiveModelConsent(false);
      api.setAccessToken(issued.access_token);
      product.setAccessToken(issued.access_token);
      try {
        const session = await api.currentSession();
        refreshToken.current = issued.refresh_token;
        setAccount(issued.account);
        setApiSession(session);
      } catch (reason) {
        refreshToken.current = undefined;
        setAccount(null);
        setApiSession(null);
        api.setAccessToken(undefined);
        product.setAccessToken(undefined);
        throw reason;
      }
    },
    [api, product, setLiveModelConsent],
  );
  const loginAccount = useCallback(
    async (email: string, password: string) => {
      await applyAccountSession(await product.login(email, password));
      notify("Đã đăng nhập. Thông tin phiên chỉ được giữ trong bộ nhớ tab.");
    },
    [applyAccountSession, notify, product],
  );
  const registerAccount = useCallback(
    async (name: string, email: string, password: string) => {
      await product.register(name, email, password);
      await loginAccount(email, password);
    },
    [loginAccount, product],
  );
  const refreshAccountSession = useCallback(async () => {
    if (!refreshToken.current)
      throw new Error("Hãy đăng nhập lại để cấp phiên mới.");
    await applyAccountSession(await product.refresh(refreshToken.current));
    notify("Đã gia hạn phiên đăng nhập trong tab.");
  }, [applyAccountSession, notify, product]);
  const updateAccountName = useCallback(
    async (name: string) => {
      if (!account) throw new Error("Hãy đăng nhập tài khoản.");
      setAccount(await product.profile(name, account.version));
      setApiSession(await api.currentSession());
    },
    [account, api, product],
  );

  const logoutApiSession = useCallback(async () => {
    let error: unknown;
    try {
      if (apiSession) await api.revokeCurrentSession();
    } catch (reason) {
      error = reason;
    } finally {
      identityEpoch.current += 1;
      setLiveModelConsent(false);
      api.setAccessToken(undefined);
      product.setAccessToken(undefined);
      refreshToken.current = undefined;
      setAccount(null);
      setHeritageFavorites([]);
      setHeritageFavoritesLoading(false);
      setSavedRunsLoading(false);
      setApiSession(null);
      setSavedRuns([]);
    }
    if (error) throw error;
    notify(
      account
        ? "Đã đăng xuất thiết bị này. Dữ liệu tài khoản được giữ trên server."
        : "Đã thu hồi phiên khách và xóa token khỏi bộ nhớ tab.",
    );
  }, [api, product, apiSession, account, notify, setLiveModelConsent]);

  const switchMode = useCallback(
    (next: FrontendMode) => {
      if (next === mode) return;
      identityEpoch.current += 1;
      setLiveModelConsent(false);
      api.setAccessToken(undefined);
      product.setAccessToken(undefined);
      refreshToken.current = undefined;
      setAccount(null);
      setHeritageFavorites([]);
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
    [api, product, mode, preview, setLiveModelConsent],
  );

  const value: AppContextValue = {
    mode,
    switchMode,
    api,
    product,
    account,
    loginAccount,
    registerAccount,
    refreshAccountSession,
    updateAccountName,
    heritageFavorites,
    heritageFavoritesLoading,
    heritageFavoritesError,
    refreshHeritageFavorites,
    setHeritageFavorite,
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
