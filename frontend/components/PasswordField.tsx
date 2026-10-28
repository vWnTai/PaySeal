"use client";

import { useId, useState, type InputHTMLAttributes } from "react";

export function PasswordField({
  label = "Mật khẩu",
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string }) {
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <div className="relative">
        <input
          {...props}
          id={id}
          type={visible ? "text" : "password"}
          className="!pr-16"
          onKeyUp={(event) => setCapsLock(event.getModifierState("CapsLock"))}
          onBlur={() => setCapsLock(false)}
        />
        <button
          type="button"
          aria-controls={id}
          aria-pressed={visible}
          aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
          onClick={() => setVisible(!visible)}
          className="absolute inset-y-0 right-1 px-3 text-xs font-semibold text-teal-700"
        >
          {visible ? "Ẩn" : "Hiện"}
        </button>
      </div>
      {capsLock && (
        <span role="status" className="hint !text-amber-700">
          Caps Lock đang bật.
        </span>
      )}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}
