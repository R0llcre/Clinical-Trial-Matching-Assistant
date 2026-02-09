import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

type ButtonTone = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: ButtonTone;
  size?: ButtonSize;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
};

const toneClass: Record<ButtonTone, string> = {
  primary: "ui-button--primary",
  secondary: "ui-button--secondary",
  ghost: "ui-button--ghost",
  danger: "ui-button--danger",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "ui-button--sm",
  md: "ui-button--md",
  lg: "ui-button--lg",
};

export function Button({
  tone = "primary",
  size = "md",
  iconLeft,
  iconRight,
  className,
  children,
  ...props
}: Props) {
  return (
    <button
      className={cx("ui-button", toneClass[tone], sizeClass[size], className)}
      {...props}
    >
      {iconLeft ? <span className="ui-button__icon">{iconLeft}</span> : null}
      <span className="ui-button__label">{children}</span>
      {iconRight ? <span className="ui-button__icon">{iconRight}</span> : null}
    </button>
  );
}

