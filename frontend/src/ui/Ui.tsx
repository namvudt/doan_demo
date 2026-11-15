import type { ButtonHTMLAttributes, ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  XCircle,
} from "lucide-react";

export function Button({
  tone = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return <button className={`button ${tone} ${className}`} {...props} />;
}

export function StatusCard({
  kind = "info",
  title,
  children,
  action,
}: {
  kind?: "info" | "success" | "warning" | "error" | "loading";
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const Icon =
    kind === "loading"
      ? LoaderCircle
      : kind === "success"
        ? CheckCircle2
        : kind === "error"
          ? XCircle
          : AlertTriangle;
  return (
    <section
      className={`status-card ${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      <Icon className={kind === "loading" ? "spin" : ""} size={21} />
      <div>
        <strong>{title}</strong>
        {children && <div className="status-copy">{children}</div>}
        {action && <div className="status-action">{action}</div>}
      </div>
    </section>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="empty-state">
      {icon && <div className="empty-icon">{icon}</div>}
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </section>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "gold" | "green" | "red" | "blue";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {error ? (
        <span className="field-error">{error}</span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </label>
  );
}
