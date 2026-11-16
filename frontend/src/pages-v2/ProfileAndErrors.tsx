import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  CircleUserRound,
  LogOut,
  RotateCcw,
  ShieldAlert,
  UserRoundCog,
} from "lucide-react";
import { useApp } from "../app/AppContext";
import { usePreview } from "../preview/PreviewProvider";
import type { PreviewRole } from "../preview/types";
import { Badge, Button, EmptyState, Field, StatusCard } from "../ui/Ui";

export function ProfilePage() {
  const app = useApp();
  const preview = usePreview();
  const navigate = useNavigate();
  const [name, setName] = useState(
    app.account?.display_name || preview.currentUser?.fullName || "",
  );
  const [busy, setBusy] = useState(false);
  const [profileError, setProfileError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setProfileError("");
    try {
      if (app.mode === "preview") {
        preview.updateProfile({ fullName: name });
        app.notify("Đã cập nhật hồ sơ mô phỏng.");
      } else {
        await app.updateAccountName(name);
        app.notify("Đã lưu tên hiển thị trên server.");
      }
    } catch (reason) {
      setProfileError(
        reason instanceof Error ? reason.message : "Không thể cập nhật hồ sơ.",
      );
    }
  };
  const logout = async () => {
    setBusy(true);
    try {
      if (app.mode === "preview") preview.logout();
      else await app.logoutApiSession();
      navigate("/login", { replace: true });
    } catch (reason) {
      app.notify(
        reason instanceof Error ? reason.message : "Không thể đăng xuất.",
        "error",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-shell profile-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">TÀI KHOẢN & PHIÊN</span>
          <h1>Không gian của bạn</h1>
          <p>
            {app.mode === "preview"
              ? "Danh tính mô phỏng chỉ tồn tại trong UI Preview."
              : app.account
                ? "Tài khoản giữ hội thoại và di sản yêu thích trên backend."
                : "Phiên khách sở hữu riêng asset, run và lịch sử trong backend."}
          </p>
        </div>
      </header>
      {app.mode === "preview" && preview.currentUser ? (
        <div className="profile-grid">
          <section className="panel profile-summary">
            <span className="profile-avatar-large">
              {preview.currentUser.fullName.slice(0, 2).toUpperCase()}
            </span>
            <h2>{preview.currentUser.fullName}</h2>
            <p>{preview.currentUser.email}</p>
            <div className="detail-badges">
              <Badge tone={preview.currentRole === "admin" ? "gold" : "blue"}>
                {preview.currentRole}
              </Badge>
              <Badge tone="green">{preview.currentUser.status}</Badge>
            </div>
            <p className="small muted">
              Danh tính hư cấu · tạo{" "}
              {new Date(preview.currentUser.createdAt).toLocaleDateString(
                "vi-VN",
              )}
            </p>
          </section>
          <section className="panel">
            <h2>Thông tin mô phỏng</h2>
            <form className="form-stack" onSubmit={submit}>
              <Field label="Tên hiển thị">
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="Email">
                <input value={preview.currentUser.email} disabled />
              </Field>
              {profileError && (
                <p className="form-alert" role="alert">
                  {profileError}
                </p>
              )}
              <Button type="submit">Lưu trong Preview</Button>
            </form>
          </section>
          <section className="panel preview-role-panel">
            <div className="section-head">
              <div>
                <h2>Chuyển vai trò Preview</h2>
                <p>Công cụ kiểm thử giao diện, không cấp quyền backend.</p>
              </div>
              <UserRoundCog size={22} />
            </div>
            <div className="role-switch">
              {(["guest", "user", "admin"] as PreviewRole[]).map((role) => (
                <button
                  key={role}
                  className={preview.currentRole === role ? "active" : ""}
                  onClick={() => {
                    setProfileError("");
                    try {
                      const user = preview.switchRole(role);
                      setName(user.fullName);
                    } catch (reason) {
                      setProfileError(
                        reason instanceof Error
                          ? reason.message
                          : "Không thể chuyển vai trò.",
                      );
                    }
                  }}
                >
                  {role}
                </button>
              ))}
            </div>
            <StatusCard kind="warning" title="Route guard chỉ là trình bày">
              Vai trò Preview chỉ thay đổi giao diện mô phỏng. Quyền biên tập
              trên server được kiểm tra theo tài khoản đã đăng nhập.
            </StatusCard>
          </section>
          <section className="panel profile-danger">
            <h2>Kết thúc phiên Preview</h2>
            <p>
              Đăng xuất không xóa catalog mô phỏng; “Đặt lại Preview” sẽ khôi
              phục toàn bộ fixture ban đầu.
            </p>
            <div className="button-row">
              <Button tone="secondary" onClick={logout} disabled={busy}>
                <LogOut size={16} /> Đăng xuất
              </Button>
              <Button
                tone="danger"
                onClick={() => {
                  if (
                    window.confirm(
                      "Khôi phục toàn bộ dữ liệu UI Preview về ban đầu?",
                    )
                  )
                    preview.resetPreview();
                }}
              >
                <RotateCcw size={16} /> Đặt lại Preview
              </Button>
            </div>
          </section>
        </div>
      ) : app.mode === "api" && app.apiSession ? (
        <div className="profile-grid api-profile-grid">
          <section className="panel profile-summary">
            <span className="profile-avatar-large">
              <CircleUserRound size={35} />
            </span>
            <h2>{app.apiSession.label}</h2>
            <p>{app.account?.email || "Guest session"}</p>
            <Badge tone="blue">{app.account?.role || "Phiên khách"}</Badge>
          </section>
          <section className="panel">
            <h2>Chi tiết phiên</h2>
            <dl className="detail-facts">
              <div>
                <dt>Session ID</dt>
                <dd className="mono">{app.apiSession.session_id}</dd>
              </div>
              <div>
                <dt>Hết hạn</dt>
                <dd>
                  {new Date(app.apiSession.expires_at).toLocaleString("vi-VN")}
                </dd>
              </div>
              <div>
                <dt>Vai trò</dt>
                <dd>
                  {app.account?.role || "Phiên khách không có quyền biên tập"}
                </dd>
              </div>
            </dl>
          </section>
          {app.account && (
            <section className="panel">
              <h2>Thông tin tài khoản</h2>
              <form className="form-stack" onSubmit={submit}>
                <Field label="Tên hiển thị">
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    maxLength={80}
                  />
                </Field>
                {profileError && (
                  <p className="form-alert" role="alert">
                    {profileError}
                  </p>
                )}
                <Button type="submit">Lưu thông tin tài khoản</Button>
                <Button
                  type="button"
                  tone="secondary"
                  onClick={() =>
                    void app
                      .refreshAccountSession()
                      .catch((reason: unknown) =>
                        setProfileError(
                          reason instanceof Error
                            ? reason.message
                            : "Không gia hạn được phiên.",
                        ),
                      )
                  }
                >
                  Gia hạn phiên đăng nhập
                </Button>
              </form>
            </section>
          )}
          <section className="panel profile-danger">
            <h2>Thu hồi phiên</h2>
            <p>
              {app.account
                ? "Đăng xuất thiết bị hiện tại. Bạn có thể đăng nhập lại để xem dữ liệu tài khoản; các thiết bị khác vẫn giữ phiên riêng."
                : "Backend sẽ thu hồi token, yêu cầu hủy các run đang queued/running và bạn sẽ mất quyền truy cập lịch sử thuộc phiên này."}
            </p>
            <Button tone="danger" onClick={logout} disabled={busy}>
              <LogOut size={16} />{" "}
              {busy ? "Đang thu hồi…" : "Thu hồi và đăng xuất"}
            </Button>
          </section>
        </div>
      ) : (
        <EmptyState
          title="Chưa có danh tính hoặc phiên"
          icon={<CircleUserRound size={28} />}
        >
          Hãy{" "}
          <Link to="/login">đăng nhập Preview hoặc truy cập phiên khách</Link>.
        </EmptyState>
      )}
    </div>
  );
}

export function ForbiddenPage() {
  const location = useLocation();
  const reason = (location.state as { reason?: string } | null)?.reason;
  return (
    <div className="page-shell centered-page">
      <EmptyState
        title="Bạn không có quyền mở trang này"
        icon={<ShieldAlert size={31} />}
      >
        {reason || "Route này cần một vai trò phù hợp."}
        <br />
        <Link to="/heritages">Trở về thư viện</Link>
      </EmptyState>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="page-shell centered-page">
      <EmptyState
        title="Không tìm thấy trang"
        icon={<span className="error-code">404</span>}
      >
        Địa chỉ có thể đã thay đổi.{" "}
        <Link to="/heritages">Trở về thư viện di sản</Link>.
      </EmptyState>
    </div>
  );
}

export function RouteErrorPage() {
  return (
    <div className="page-shell centered-page">
      <StatusCard kind="error" title="Không thể hiển thị trang">
        <p>
          Đã xảy ra lỗi giao diện ngoài dự kiến. Dữ liệu API không được thay thế
          bằng fixture.
        </p>
        <Button onClick={() => window.location.reload()}>
          Tải lại ứng dụng
        </Button>
      </StatusCard>
    </div>
  );
}
