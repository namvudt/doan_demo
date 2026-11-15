import { NavLink, Outlet } from "react-router-dom";
import {
  Database,
  Gauge,
  Landmark,
  MessagesSquare,
  PlaySquare,
  UsersRound,
} from "lucide-react";

export function AdminLayout() {
  return (
    <div className="admin-shell page-shell">
      <header className="page-heading admin-heading">
        <div>
          <span className="eyebrow">UI PREVIEW · QUẢN TRỊ</span>
          <h1>Không gian quản trị</h1>
          <p>
            Các thay đổi mô phỏng dùng chung catalog với trang công khai và bản
            đồ.
          </p>
        </div>
      </header>
      <nav className="admin-tabs" aria-label="Các mô-đun quản trị">
        <NavLink to="/admin" end>
          <Gauge size={17} /> Tổng quan
        </NavLink>
        <NavLink to="/admin/heritages">
          <Landmark size={17} /> Di sản
        </NavLink>
        <NavLink to="/admin/users">
          <UsersRound size={17} /> Người dùng
        </NavLink>
        <NavLink to="/admin/sources">
          <Database size={17} /> Nguồn
        </NavLink>
        <NavLink to="/admin/runs">
          <PlaySquare size={17} /> Run
        </NavLink>
        <NavLink to="/admin/feedback">
          <MessagesSquare size={17} /> Phản hồi
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
