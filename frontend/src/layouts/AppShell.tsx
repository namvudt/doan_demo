import { useState } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  BookHeart,
  ChevronRight,
  CircleUserRound,
  Landmark,
  LayoutDashboard,
  LogIn,
  Map,
  Menu,
  MessageSquareText,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useApp } from "../app/AppContext";
import { evaluateRunModelMode } from "../api/contracts";
import { usePreview } from "../preview/PreviewProvider";
import { Badge, Button } from "../ui/Ui";
import { BackendConnection } from "../ui/BackendConnection";

const pageNames: Record<string, string> = {
  chat: "Hỏi đáp hình ảnh",
  heritages: "Thư viện di sản",
  map: "Bản đồ",
  favorites: "Mục đã lưu",
  profile: "Hồ sơ",
  admin: "Quản trị",
  forbidden: "Không có quyền",
};

function NavItem({
  to,
  icon,
  children,
  end,
}: {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  end?: boolean;
}) {
  return (
    <NavLink to={to} end={end}>
      {icon}
      <span>{children}</span>
    </NavLink>
  );
}

export function AppShell() {
  const app = useApp();
  const preview = usePreview();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const segment =
    location.pathname.split("/").filter(Boolean)[0] || "heritages";
  const identity =
    app.mode === "preview" ? preview.currentUser : app.apiSession;
  const runGate = evaluateRunModelMode(app.capabilities, {
    allowLiveModelCalls: app.allowLiveModelCalls,
    liveModelConsent: app.liveModelConsent,
  });

  const closeAnd = (path: string) => {
    setMobileOpen(false);
    navigate(path);
  };

  return (
    <div className="app-shell-v2">
      <a href="#main-content" className="skip-link">
        Đến nội dung chính
      </a>
      {mobileOpen && (
        <button
          className="nav-backdrop"
          aria-label="Đóng điều hướng"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside
        className={`app-sidebar ${mobileOpen ? "open" : ""}`}
        id="primary-navigation"
      >
        <div className="sidebar-head">
          <Link
            to="/heritages"
            className="brand"
            onClick={() => setMobileOpen(false)}
          >
            <span className="brand-mark">
              <Landmark size={23} />
            </span>
            <span>
              <strong>
                di sản<span>.</span>
              </strong>
              <small>HERITAGE INTELLIGENCE</small>
            </span>
          </Link>
          <button
            className="icon-button mobile-only"
            aria-label="Đóng điều hướng"
            onClick={() => setMobileOpen(false)}
          >
            <X size={20} />
          </button>
        </div>
        <p className="nav-label">KHÔNG GIAN KHÁM PHÁ</p>
        <nav
          className="main-nav"
          aria-label="Điều hướng chính"
          onClick={() => setMobileOpen(false)}
        >
          <NavItem to="/chat" icon={<MessageSquareText size={19} />}>
            Hỏi đáp <Badge tone="gold">AI</Badge>
          </NavItem>
          <NavItem to="/heritages" icon={<Landmark size={19} />}>
            Di sản
          </NavItem>
          <NavItem to="/map" icon={<Map size={19} />}>
            Bản đồ
          </NavItem>
          <NavItem to="/favorites" icon={<BookHeart size={19} />}>
            Mục đã lưu
          </NavItem>
        </nav>
        {app.mode === "preview" && preview.currentRole === "admin" && (
          <>
            <p className="nav-label admin-label">QUẢN TRỊ PREVIEW</p>
            <nav
              className="main-nav"
              aria-label="Điều hướng quản trị"
              onClick={() => setMobileOpen(false)}
            >
              <NavItem to="/admin" icon={<LayoutDashboard size={19} />} end>
                Tổng quan
              </NavItem>
              <NavItem to="/admin/heritages" icon={<Landmark size={19} />}>
                Nội dung
              </NavItem>
              <NavItem to="/admin/users" icon={<ShieldCheck size={19} />}>
                Người dùng
              </NavItem>
            </nav>
          </>
        )}
        <div className="sidebar-spacer" />
        <div className="mode-card">
          <span className="eyebrow">NGUỒN DỮ LIỆU</span>
          <strong>
            {app.mode === "preview" ? "UI Preview" : "Backend API"}
          </strong>
          <p>
            {app.mode === "preview"
              ? "Fixture biệt lập trong bộ nhớ trình duyệt."
              : app.capabilities
                ? `Backend ${app.capabilities.model_mode}`
                : "Chưa xác định chế độ backend."}
          </p>
          <button onClick={() => setSettingsOpen(true)}>
            <Settings2 size={15} /> Đổi chế độ
          </button>
        </div>
        <div className="sidebar-profile">
          <span className="avatar">
            {app.mode === "preview"
              ? preview.currentUser?.fullName.slice(0, 2).toUpperCase() || "G"
              : "API"}
          </span>
          <div>
            <strong>
              {app.mode === "preview"
                ? preview.currentUser?.fullName || "Khách Preview"
                : app.apiSession?.label || "Chưa có phiên"}
            </strong>
            <small>
              {app.mode === "preview"
                ? preview.currentRole
                : app.apiSession
                  ? "Phiên khách"
                  : "API Integration"}
            </small>
          </div>
          {identity ? (
            <button
              className="icon-button"
              aria-label="Mở hồ sơ"
              onClick={() => closeAnd("/profile")}
            >
              <CircleUserRound size={18} />
            </button>
          ) : (
            <button
              className="icon-button"
              aria-label="Đăng nhập"
              onClick={() => closeAnd("/login")}
            >
              <LogIn size={18} />
            </button>
          )}
        </div>
      </aside>

      <div className="app-main-shell">
        <header className="app-topbar">
          <div className="topbar-path">
            <button
              className="icon-button mobile-only"
              aria-label="Mở điều hướng"
              aria-expanded={mobileOpen}
              aria-controls="primary-navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={21} />
            </button>
            <Link to="/heritages">Di Sản</Link>
            <ChevronRight size={14} />
            <strong>{pageNames[segment] || "Ứng dụng"}</strong>
          </div>
          <div className="topbar-actions">
            <button
              type="button"
              aria-label="Mở trạng thái kết nối"
              onClick={() => setSettingsOpen(true)}
              className={`connection-pill ${app.mode === "api" && app.capabilities?.model_mode !== "demo" ? "warning" : ""}`}
            >
              <span />
              {app.mode === "preview"
                ? "Preview"
                : app.capabilities?.model_mode === "demo"
                  ? "API demo"
                  : app.capabilities?.model_mode === "live"
                    ? "AI live"
                    : "API chưa sẵn sàng"}
            </button>
            {identity ? (
              <Link className="topbar-profile-link" to="/profile">
                Hồ sơ
              </Link>
            ) : (
              <Link className="button secondary compact" to="/login">
                Truy cập
              </Link>
            )}
          </div>
        </header>
        {app.mode === "preview" ? (
          <div className="preview-banner" role="status">
            <Sparkles size={14} />
            <strong>UI Preview — Dữ liệu mô phỏng, chưa lưu lên backend</strong>
            <span>Vai trò: {preview.currentRole}</span>
          </div>
        ) : (
          <div
            className={`api-banner ${runGate.allowed ? "ok" : "blocked"}`}
            role="status"
          >
            <ShieldCheck size={14} />
            <strong>
              {app.capabilities?.model_mode === "demo"
                ? "API Integration — backend xác nhận model_mode=demo"
                : app.capabilities?.model_mode === "live"
                  ? runGate.allowed
                    ? "API Integration — AI thật · tác vụ có thể tính phí"
                    : `API Integration — ${runGate.message}`
                  : "API Integration — đang chờ xác minh chế độ AI của backend"}
            </strong>
          </div>
        )}
        <main id="main-content">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>DI SẢN VIỆT NAM</span>
          <span>Run đã lưu ≠ di sản yêu thích ≠ nguồn chứng cứ</span>
          <span>Frontend · v1</span>
        </footer>
      </div>

      {settingsOpen && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={() => setSettingsOpen(false)}
        >
          <section
            className="dialog-card settings-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mode-title"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="dialog-head">
              <div>
                <span className="eyebrow">MÔI TRƯỜNG FRONTEND</span>
                <h2 id="mode-title">Chọn nguồn dữ liệu</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Đóng"
                onClick={() => setSettingsOpen(false)}
              >
                <X size={19} />
              </button>
            </div>
            <p>
              Hai chế độ được cách ly. Lỗi API không bao giờ tự chuyển sang dữ
              liệu mô phỏng.
            </p>
            <div className="mode-options">
              <button
                className={app.mode === "preview" ? "selected" : ""}
                onClick={() => app.switchMode("preview")}
              >
                <Sparkles size={21} />
                <span>
                  <strong>UI Preview</strong>
                  <small>
                    Luồng tài khoản, catalog, bản đồ và admin mô phỏng.
                  </small>
                </span>
              </button>
              <button
                className={app.mode === "api" ? "selected" : ""}
                onClick={() => app.switchMode("api")}
              >
                <ShieldCheck size={21} />
                <span>
                  <strong>API Integration</strong>
                  <small>
                    Phiên khách và VQA theo backend thật; không fallback.
                  </small>
                </span>
              </button>
            </div>
            <BackendConnection />
            <div className="dialog-actions">
              <Button tone="secondary" onClick={() => setSettingsOpen(false)}>
                Đóng
              </Button>
              <Button
                onClick={() => {
                  setSettingsOpen(false);
                  navigate("/login");
                }}
              >
                Tiếp tục
              </Button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
