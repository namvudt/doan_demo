import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useApp } from "./AppContext";
import { usePreview } from "../preview/PreviewProvider";

export function RequireIdentity() {
  const app = useApp();
  const preview = usePreview();
  const location = useLocation();
  const allowed =
    app.mode === "preview" ? preview.isAuthenticated : Boolean(app.apiSession);
  return allowed ? (
    <Outlet />
  ) : (
    <Navigate
      to="/login"
      replace
      state={{ from: `${location.pathname}${location.search}` }}
    />
  );
}

export function RequireAdmin() {
  const app = useApp();
  const preview = usePreview();
  const location = useLocation();
  if (app.mode !== "preview")
    return (
      <Navigate
        to="/forbidden"
        replace
        state={{ reason: "API hiện không có danh tính/RBAC quản trị." }}
      />
    );
  if (!preview.isAuthenticated)
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  if (preview.currentRole !== "admin")
    return (
      <Navigate
        to="/forbidden"
        replace
        state={{ reason: "Cần vai trò quản trị viên trong UI Preview." }}
      />
    );
  return <Outlet />;
}
