import type { ReactNode } from "react";

import { cx } from "./cx";

export type TabItem = {
  id: string;
  label: string;
  count?: number;
  disabled?: boolean;
};

type Props = {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  className?: string;
  ariaLabel?: string;
  rightSlot?: ReactNode;
};

export function Tabs({
  items,
  activeId,
  onChange,
  className,
  ariaLabel = "Tabs",
  rightSlot,
}: Props) {
  return (
    <div className={cx("ui-tabs", className)}>
      <div className="ui-tabs__rail" role="tablist" aria-label={ariaLabel}>
        {items.map((item) => {
          const active = item.id === activeId;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={active}
              disabled={item.disabled}
              className={cx(
                "ui-tab",
                active ? "ui-tab--active" : null,
                item.disabled ? "ui-tab--disabled" : null
              )}
              onClick={() => onChange(item.id)}
            >
              <span className="ui-tab__label">{item.label}</span>
              {typeof item.count === "number" ? (
                <span className="ui-tab__count">{item.count}</span>
              ) : null}
            </button>
          );
        })}
      </div>
      {rightSlot ? <div className="ui-tabs__right">{rightSlot}</div> : null}
    </div>
  );
}

