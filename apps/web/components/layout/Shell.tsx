import type { ReactNode } from "react";

import { cx } from "../ui/cx";

type Props = {
  kicker?: string;
  title?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Shell({
  kicker,
  title,
  subtitle,
  actions,
  children,
  className,
}: Props) {
  const hasHeader = Boolean(kicker || title || subtitle || actions);

  return (
    <main className={cx("ui-shell", className)}>
      {hasHeader ? (
        <header className="ui-shell__header">
          <div className="ui-shell__heading">
            {kicker ? <div className="ui-shell__kicker">{kicker}</div> : null}
            {title ? <h1 className="ui-shell__title">{title}</h1> : null}
            {subtitle ? <div className="ui-shell__subtitle">{subtitle}</div> : null}
          </div>
          {actions ? <div className="ui-shell__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="ui-shell__body">{children}</div>
    </main>
  );
}

