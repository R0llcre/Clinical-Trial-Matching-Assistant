import type { HTMLAttributes } from "react";

import { cx } from "./cx";

type BadgeTone = "neutral" | "brand" | "success" | "warning" | "danger";

type Props = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

const toneClass: Record<BadgeTone, string> = {
  neutral: "ui-badge--neutral",
  brand: "ui-badge--brand",
  success: "ui-badge--success",
  warning: "ui-badge--warning",
  danger: "ui-badge--danger",
};

export function Badge({ tone = "neutral", className, ...props }: Props) {
  return (
    <span className={cx("ui-badge", toneClass[tone], className)} {...props} />
  );
}

