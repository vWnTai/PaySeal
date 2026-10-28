import type { ButtonHTMLAttributes, ReactNode } from "react";

type LoadingButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  busy: boolean;
  busyLabel: string;
  children: ReactNode;
};

export function LoadingButton({
  busy,
  busyLabel,
  children,
  disabled,
  className = "btn-primary",
  ...props
}: LoadingButtonProps) {
  return (
    <button {...props} className={className} disabled={disabled || busy} aria-busy={busy}>
      {busy ? (
        <>
          <span className="spinner" aria-hidden="true" />
          {busyLabel}
        </>
      ) : (
        children
      )}
    </button>
  );
}
