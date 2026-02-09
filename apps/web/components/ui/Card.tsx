import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

type CardTone = "default" | "subtle" | "elevated";

type Props = HTMLAttributes<HTMLDivElement> & {
  tone?: CardTone;
  children: ReactNode;
};

const toneClass: Record<CardTone, string> = {
  default: "ui-card--default",
  subtle: "ui-card--subtle",
  elevated: "ui-card--elevated",
};

export function Card({ tone = "default", className, children, ...props }: Props) {
  return (
    <div className={cx("ui-card", toneClass[tone], className)} {...props}>
      {children}
    </div>
  );
}

