import type { InputHTMLAttributes } from "react";

import { cx } from "./cx";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

export function Input({ invalid, className, ...props }: Props) {
  return (
    <input
      className={cx("ui-input", invalid ? "ui-input--invalid" : null, className)}
      {...props}
    />
  );
}

