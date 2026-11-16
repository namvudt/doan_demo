import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppProvider } from "./app/AppContext";
import { RequireAdmin, RequireIdentity } from "./app/Guards";
import { PreviewProvider } from "./preview/PreviewProvider";
import { AppShell } from "./layouts/AppShell";
import { AdminLayout } from "./layouts/AdminLayout";
import {
  ForbiddenPage,
  NotFoundPage,
  ProfilePage,
  RouteErrorPage,
} from "./pages-v2/ProfileAndErrors";
import "./styles.css";

const page = <T extends Record<string, unknown>, K extends keyof T>(
  loader: () => Promise<T>,
  name: K,
) =>
  React.lazy(async () => ({
    default: (await loader())[name] as React.ComponentType,
  }));
const LoginPage = page(() => import("./pages-v2/AuthPages"), "LoginPage");
const RegisterPage = page(() => import("./pages-v2/AuthPages"), "RegisterPage");
const ForgotPasswordPage = page(
  () => import("./pages-v2/AuthPages"),
  "ForgotPasswordPage",
);
const ResetPasswordPage = page(
  () => import("./pages-v2/AuthPages"),
  "ResetPasswordPage",
);
const ChatPage = page(() => import("./pages-v2/ChatPages"), "ChatPage");
const RunDetailPage = page(
  () => import("./pages-v2/ChatPages"),
  "RunDetailPage",
);
const HeritagesPage = page(
  () => import("./pages-v2/HeritagePages"),
  "HeritagesPage",
);
const HeritageDetailPage = page(
  () => import("./pages-v2/HeritagePages"),
  "HeritageDetailPage",
);
const FavoritesPage = page(
  () => import("./pages-v2/FavoritesPage"),
  "FavoritesPage",
);
const MapPage = page(() => import("./pages-v2/MapPage"), "MapPage");
const AdminDashboardPage = page(
  () => import("./pages-v2/AdminPages"),
  "AdminDashboardPage",
);
const AdminFeedbackPage = page(
  () => import("./pages-v2/AdminPages"),
  "AdminFeedbackPage",
);
const AdminHeritagesPage = page(
  () => import("./pages-v2/AdminPages"),
  "AdminHeritagesPage",
);
const AdminRunsPage = page(
  () => import("./pages-v2/AdminPages"),
  "AdminRunsPage",
);
const AdminSourcesPage = page(
  () => import("./pages-v2/AdminPages"),
  "AdminSourcesPage",
);
const AdminUsersPage = page(
  () => import("./pages-v2/AdminPages"),
  "AdminUsersPage",
);
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <RouteErrorPage /> : this.props.children;
  }
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/heritages" replace />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/runs/:runId" element={<RunDetailPage />} />
        <Route path="/heritages" element={<HeritagesPage />} />
        <Route path="/heritages/:heritageId" element={<HeritageDetailPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route element={<RequireIdentity />}>
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
        </Route>
        <Route path="/forbidden" element={<ForbiddenPage />} />
        <Route element={<RequireAdmin />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminDashboardPage />} />
            <Route path="heritages" element={<AdminHeritagesPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="sources" element={<AdminSourcesPage />} />
            <Route path="runs" element={<AdminRunsPage />} />
            <Route path="feedback" element={<AdminFeedbackPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <PreviewProvider>
        <AppProvider>
          <ErrorBoundary>
            <React.Suspense
              fallback={
                <div className="route-loading" role="status">
                  Đang tải trang…
                </div>
              }
            >
              <AppRoutes />
            </React.Suspense>
          </ErrorBoundary>
        </AppProvider>
      </PreviewProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
