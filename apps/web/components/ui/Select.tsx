import type { SelectHTMLAttributes } from "react";

import { cx } from "./cx";

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean;
};

export function Select({ invalid, className, children, ...props }: Props) {
  return (
    <select
      className={cx("ui-select", invalid ? "ui-select--invalid" : null, className)}
      {...props}
    >
      {children}
    </select>
  );
}

