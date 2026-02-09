import type { ReactNode } from "react";

import { cx } from "./cx";

type ToastTone = "neutral" | "success" | "warning" | "danger";

type Props = {
  title: string;
  description?: ReactNode;
  tone?: ToastTone;
  className?: string;
};

const toneClass: Record<ToastTone, string> = {
  neutral: "ui-toast--neutral",
  success: "ui-toast--success",
  warning: "ui-toast--warning",
  danger: "ui-toast--danger",
};

export function Toast({
  title,
  description,
  tone = "neutral",
  className,
}: Props) {
  return (
    <div className={cx("ui-toast", toneClass[tone], className)} role="status">
      <div className="ui-toast__title">{title}</div>
      {description ? <div className="ui-toast__desc">{description}</div> : null}
    </div>
  );
}

