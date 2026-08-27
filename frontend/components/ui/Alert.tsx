import React from "react";

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "info" | "success" | "warning" | "error";
  icon?: React.ReactNode;
}

export function Alert({
  className = "",
  variant = "info",
  icon,
  children,
  ...props
}: AlertProps) {
  const variantStyles = {
    info: "bg-blue-50/70 border-blue-200 text-blue-900 dark:bg-blue-950/40 dark:border-blue-800 dark:text-blue-200",
    success:
      "bg-emerald-50/70 border-emerald-200 text-emerald-900 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-200",
    warning:
      "bg-amber-50/70 border-amber-200 text-amber-900 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-200",
    error:
      "bg-red-50/70 border-red-200 text-red-900 dark:bg-red-950/40 dark:border-red-800 dark:text-red-200",
  }[variant];

  return (
    <div
      role="alert"
      className={`relative w-full rounded-lg border p-3.5 text-sm flex gap-3 items-start ${variantStyles} ${className}`}
      {...props}
    >
      {icon && <div className="shrink-0 mt-0.5">{icon}</div>}
      <div className="flex-1 leading-relaxed">{children}</div>
    </div>
  );
}

export function AlertTitle({
  className = "",
  children,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h5
      className={`font-semibold tracking-tight leading-none mb-1 ${className}`}
      {...props}
    >
      {children}
    </h5>
  );
}

export function AlertDescription({
  className = "",
  children,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <div className={`text-xs opacity-90 ${className}`} {...props}>
      {children}
    </div>
  );
}
