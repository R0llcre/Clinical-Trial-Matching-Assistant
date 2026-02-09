import type { ReactNode } from "react";

import { cx } from "./cx";

type Props = {
  title: ReactNode;
  children: ReactNode;
  open: boolean;
  onToggle: () => void;
  className?: string;
};

export function Accordion({ title, children, open, onToggle, className }: Props) {
  return (
    <section className={cx("ui-accordion", className)}>
      <button
        type="button"
        className={cx("ui-accordion__button", open ? "is-open" : null)}
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className="ui-accordion__title">{title}</span>
        <span className="ui-accordion__chev" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>
      {open ? <div className="ui-accordion__panel">{children}</div> : null}
    </section>
  );
}

