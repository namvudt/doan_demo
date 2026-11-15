import { useState, type FormEvent } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowLeft,
  Eye,
  EyeOff,
  KeyRound,
  Landmark,
  ShieldCheck,
} from "lucide-react";
import { useApp } from "../app/AppContext";
import { usePreview } from "../preview/PreviewProvider";
import { PreviewValidationError } from "../preview/types";
import { Button, Field, StatusCard } from "../ui/Ui";

function safeReturnTo(value: unknown) {
  return typeof value === "string" &&
    value.startsWith("/") &&
    !value.startsWith("//")
    ? value
    : "/chat";
}

function AuthFrame({
  eyebrow,
  title,
  description,
  children,
  footer,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="Giới thiệu ứng dụng">
        <Link to="/heritages" className="auth-brand">
          <span className="brand-mark">
            <Landmark size={25} />
          </span>
          <span>
            <strong>di sản.</strong>
            <small>HERITAGE INTELLIGENCE</small>
          </span>
        </Link>
        <div className="auth-quote">
          <span className="eyebrow">KHÔNG GIAN KHÁM PHÁ</span>
          <blockquote>
            Quan sát có căn cứ.
            <br />
            Kể chuyện có nguồn.
          </blockquote>
          <p>
            Khám phá di sản Việt Nam qua hình ảnh, tư liệu và một quy trình AI
            minh bạch.
          </p>
        </div>
        <div className="auth-assurance">
          <ShieldCheck size={17} /> Bản xem trước không tạo tài khoản thật
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <Link to="/heritages" className="back-link">
            <ArrowLeft size={15} /> Về trang khám phá
          </Link>
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p className="lead">{description}</p>
          {children}
          {footer && <div className="auth-footer">{footer}</div>}
        </div>
      </section>
    </main>
  );
}

export function LoginPage() {
  const app = useApp();
  const preview = usePreview();
  const navigate = useNavigate();
  const location = useLocation();
  const returnTo = safeReturnTo(
    (location.state as { from?: string } | null)?.from,
  );
  const [email, setEmail] = useState("user@preview.local");
  const [password, setPassword] = useState("Demo123!");
  const [token, setToken] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (app.mode === "preview" && preview.isAuthenticated)
    return <Navigate to={returnTo} replace />;
  if (app.mode === "api" && app.apiSession)
    return <Navigate to={returnTo} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (app.mode === "preview") {
        preview.login({ email, password });
      } else if (token.trim()) {
        await app.attachGuestToken(token.trim());
        setToken("");
      } else {
        await app.createGuestSession("Heritage Web");
      }
      navigate(returnTo, { replace: true });
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Không thể tiếp tục.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame
      eyebrow={app.mode === "preview" ? "UI PREVIEW" : "API INTEGRATION"}
      title={
        app.mode === "preview" ? "Chào mừng trở lại" : "Truy cập phiên khách"
      }
      description={
        app.mode === "preview"
          ? "Chỉ dùng danh tính giả bên dưới. Mật khẩu không được lưu hoặc gửi đến backend."
          : "Backend hiện có phiên khách Bearer, không có đăng nhập email/mật khẩu."
      }
      footer={
        app.mode === "preview" ? (
          <p>
            Chưa có hồ sơ? <Link to="/register">Tạo tài khoản mô phỏng</Link>
          </p>
        ) : (
          <p>
            Đăng ký, khôi phục mật khẩu và vai trò tài khoản chưa được backend
            hỗ trợ.
          </p>
        )
      }
    >
      <form className="form-stack" onSubmit={submit} noValidate>
        {app.mode === "preview" ? (
          <>
            <Field
              label="Email mô phỏng"
              hint="user@preview.local hoặc admin@preview.local"
            >
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
                required
              />
            </Field>
            <Field label="Mật khẩu mô phỏng" hint="Demo123!">
              <span className="input-with-action">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="off"
                  required
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  onClick={() => setShowPassword((v) => !v)}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </span>
            </Field>
            <div className="form-row-between">
              <span className="muted small">Không dùng thông tin thật.</span>
              <Link to="/forgot-password">Quên mật khẩu?</Link>
            </div>
          </>
        ) : (
          <>
            {app.capabilities?.session_bootstrap_required ? (
              <StatusCard kind="warning" title="Backend yêu cầu bootstrap">
                Trình duyệt không được nhận bootstrap token. Hãy dán guest
                access token do operator cấp.
              </StatusCard>
            ) : (
              <StatusCard kind="info" title="Có thể tạo phiên khách">
                Phiên mới chỉ sở hữu ảnh và lịch sử run của chính phiên đó. Đăng
                xuất sẽ thu hồi phiên và hủy run đang hoạt động.
              </StatusCard>
            )}
            <Field
              label="Guest access token (nếu đã được cấp)"
              hint="Chỉ giữ trong bộ nhớ tab; không ghi vào URL hoặc localStorage."
            >
              <span className="input-with-action">
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  autoComplete="off"
                />
                <KeyRound size={17} />
              </span>
            </Field>
          </>
        )}
        {error && (
          <p className="form-alert" role="alert">
            {error}
          </p>
        )}
        <Button
          type="submit"
          disabled={
            busy ||
            (app.mode === "api" &&
              app.capabilities?.session_bootstrap_required &&
              !token.trim())
          }
        >
          {busy
            ? "Đang xác thực…"
            : app.mode === "preview"
              ? "Đăng nhập Preview"
              : token.trim()
                ? "Dùng token được cấp"
                : "Tạo phiên khách"}
        </Button>
      </form>
    </AuthFrame>
  );
}

export function RegisterPage() {
  const app = useApp();
  const preview = usePreview();
  const navigate = useNavigate();
  const [values, setValues] = useState({
    fullName: "",
    email: "",
    password: "",
    passwordConfirmation: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const update =
    (key: keyof typeof values) =>
    (event: React.ChangeEvent<HTMLInputElement>) =>
      setValues((current) => ({ ...current, [key]: event.target.value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (app.mode !== "preview") return;
    setBusy(true);
    setError("");
    setErrors({});
    try {
      preview.register(values);
      navigate("/profile", { replace: true });
    } catch (reason) {
      if (reason instanceof PreviewValidationError) setErrors(reason.fields);
      setError(
        reason instanceof Error
          ? reason.message
          : "Không thể tạo hồ sơ mô phỏng.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame
      eyebrow="HỒ SƠ MÔ PHỎNG"
      title="Tạo không gian của bạn"
      description="Luồng này chỉ hoạt động trong UI Preview; không tạo tài khoản hoặc gửi email thật."
      footer={
        <p>
          Đã có hồ sơ Preview? <Link to="/login">Đăng nhập</Link>
        </p>
      }
    >
      {app.mode !== "preview" ? (
        <StatusCard kind="warning" title="Đăng ký chưa được API hỗ trợ">
          Backend chỉ có phiên khách.{" "}
          <Link to="/login">Đi đến truy cập phiên khách</Link>.
        </StatusCard>
      ) : (
        <form className="form-stack" onSubmit={submit} noValidate>
          <Field label="Họ và tên mô phỏng" error={errors.fullName}>
            <input
              value={values.fullName}
              onChange={update("fullName")}
              aria-invalid={Boolean(errors.fullName)}
              autoComplete="off"
            />
          </Field>
          <Field label="Email mô phỏng" error={errors.email}>
            <input
              type="email"
              value={values.email}
              onChange={update("email")}
              aria-invalid={Boolean(errors.email)}
              autoComplete="off"
            />
          </Field>
          <div className="form-grid-2">
            <Field label="Mật khẩu mô phỏng" error={errors.password}>
              <input
                type="password"
                value={values.password}
                onChange={update("password")}
                aria-invalid={Boolean(errors.password)}
                autoComplete="off"
              />
            </Field>
            <Field
              label="Xác nhận mật khẩu"
              error={errors.passwordConfirmation}
            >
              <input
                type="password"
                value={values.passwordConfirmation}
                onChange={update("passwordConfirmation")}
                aria-invalid={Boolean(errors.passwordConfirmation)}
                autoComplete="off"
              />
            </Field>
          </div>
          <p className="small muted">
            Tài khoản công khai luôn bắt đầu với vai trò người dùng; không thể
            tự chọn quản trị viên.
          </p>
          {error && (
            <p className="form-alert" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? "Đang tạo…" : "Tạo hồ sơ Preview"}
          </Button>
        </form>
      )}
    </AuthFrame>
  );
}

export function ForgotPasswordPage() {
  const app = useApp();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  return (
    <AuthFrame
      eyebrow="KHÔI PHỤC"
      title="Quên mật khẩu"
      description="Màn hình mô phỏng để kiểm tra trạng thái giao diện; không có email nào được gửi."
    >
      {app.mode !== "preview" ? (
        <StatusCard
          kind="warning"
          title="Backend không có API khôi phục mật khẩu"
        >
          Hãy dùng guest access token do operator cấp hoặc tạo phiên khách nếu
          được phép.
        </StatusCard>
      ) : sent ? (
        <StatusCard kind="success" title="Đã mô phỏng gửi hướng dẫn">
          Không có email thật được gửi. Bạn có thể mở{" "}
          <Link to="/reset-password?token=preview-reset">màn hình đặt lại</Link>
          .
        </StatusCard>
      ) : (
        <form
          className="form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (email.includes("@")) setSent(true);
          }}
        >
          <Field label="Email mô phỏng">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="off"
            />
          </Field>
          <Button type="submit">Mô phỏng gửi hướng dẫn</Button>
        </form>
      )}
      <div className="auth-footer">
        <p>
          <Link to="/login">Trở lại đăng nhập</Link>
        </p>
      </div>
    </AuthFrame>
  );
}

export function ResetPasswordPage() {
  const app = useApp();
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [done, setDone] = useState(false);
  const validToken = params.get("token") === "preview-reset";
  return (
    <AuthFrame
      eyebrow="ĐẶT LẠI"
      title="Đặt mật khẩu mới"
      description="Chỉ mô phỏng trạng thái thành công, hết hạn và xác thực biểu mẫu."
    >
      {app.mode !== "preview" ? (
        <StatusCard kind="warning" title="Không có API đặt lại mật khẩu" />
      ) : !validToken ? (
        <StatusCard
          kind="error"
          title="Liên kết mô phỏng không hợp lệ hoặc đã hết hạn"
        >
          <Link to="/forgot-password">Yêu cầu lại</Link>
        </StatusCard>
      ) : done ? (
        <StatusCard kind="success" title="Đã đổi mật khẩu mô phỏng">
          <Link to="/login">Trở lại đăng nhập</Link>
        </StatusCard>
      ) : (
        <form
          className="form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (password.length >= 8 && password === confirmation)
              setDone(true);
          }}
        >
          <Field
            label="Mật khẩu mới"
            error={
              password && password.length < 8
                ? "Cần ít nhất 8 ký tự."
                : undefined
            }
          >
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="off"
            />
          </Field>
          <Field
            label="Xác nhận mật khẩu"
            error={
              confirmation && confirmation !== password
                ? "Hai mật khẩu chưa khớp."
                : undefined
            }
          >
            <input
              type="password"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
              autoComplete="off"
            />
          </Field>
          <Button type="submit">Đổi mật khẩu mô phỏng</Button>
        </form>
      )}
    </AuthFrame>
  );
}
