import type { HTMLAttributes } from "react";

import { cx } from "./cx";

type Props = HTMLAttributes<HTMLDivElement> & {
  variant?: "line" | "block";
  width?: "short" | "medium" | "long";
};

export function Skeleton({
  variant = "line",
  width = "long",
  className,
  ...props
}: Props) {
  return (
    <div
      className={cx(
        "ui-skeleton",
        variant === "block" ? "ui-skeleton--block" : "ui-skeleton--line",
        width ? `ui-skeleton--${width}` : null,
        className
      )}
      {...props}
    />
  );
}

