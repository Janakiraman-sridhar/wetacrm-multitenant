import { useCallback, useEffect, useState } from "react";

const KEY = "weta_hide_values";

/**
 * The KPI privacy toggle: hide every figure on screen at once.
 *
 * An agent screen-sharing, or sitting beside a customer, should be able to blank
 * the book premium and counts without leaving the page.
 *
 * Read synchronously from `localStorage` on first render, so a hidden dashboard
 * never flashes its numbers before the preference loads.
 */
function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** Notifies every hook instance, so the whole page toggles together. */
const listeners = new Set<(hidden: boolean) => void>();

export function useValuePrivacy() {
  const [hidden, setHidden] = useState<boolean>(read);

  useEffect(() => {
    const listener = (next: boolean) => setHidden(next);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const toggle = useCallback(() => {
    const next = !read();
    try {
      localStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      /* storage unavailable — the toggle still works for this page view */
    }
    listeners.forEach((listener) => listener(next));
  }, []);

  /** Render a value, or a placeholder of the same shape when hidden. */
  const show = useCallback(
    (value: string | number | null | undefined, placeholder = "••••") =>
      hidden ? placeholder : value ?? "—",
    [hidden]
  );

  return { hidden, toggle, show };
}
