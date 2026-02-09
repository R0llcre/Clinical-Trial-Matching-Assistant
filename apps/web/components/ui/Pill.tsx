import type { HTMLAttributes } from "react";

import { cx } from "./cx";

type PillTone =
  | "neutral"
  | "brand"
  | "success"
  | "warning"
  | "danger"
  | "info";

type Props = HTMLAttributes<HTMLSpanElement> & {
  tone?: PillTone;
};

const toneClass: Record<PillTone, string> = {
  neutral: "ui-pill--neutral",
  brand: "ui-pill--brand",
  success: "ui-pill--success",
  warning: "ui-pill--warning",
  danger: "ui-pill--danger",
  info: "ui-pill--info",
};

export function Pill({ tone = "neutral", className, ...props }: Props) {
  return <span className={cx("ui-pill", toneClass[tone], className)} {...props} />;
}

