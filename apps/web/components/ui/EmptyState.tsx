import type { ReactNode } from "react";

import { cx } from "./cx";

type Props = {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  className?: string;
};

export function EmptyState({
  title,
  description,
  actions,
  icon,
  className,
}: Props) {
  return (
    <section className={cx("ui-empty", className)}>
      {icon ? <div className="ui-empty__icon">{icon}</div> : null}
      <div className="ui-empty__body">
        <h2 className="ui-empty__title">{title}</h2>
        {description ? <div className="ui-empty__desc">{description}</div> : null}
        {actions ? <div className="ui-empty__actions">{actions}</div> : null}
      </div>
    </section>
  );
}

