import type { ReactNode } from "react";

import { cx } from "./cx";

type Props = {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Field({ label, htmlFor, hint, error, children, className }: Props) {
  return (
    <div className={cx("ui-field", className)}>
      <label className="ui-field__label" htmlFor={htmlFor}>
        {label}
      </label>
      <div className="ui-field__control">{children}</div>
      {error ? <div className="ui-field__error">{error}</div> : null}
      {hint ? <div className="ui-field__hint">{hint}</div> : null}
    </div>
  );
}

