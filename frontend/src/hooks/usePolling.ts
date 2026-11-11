"use client";
import { useEffect, useRef } from "react";

/** Calls `fn` every `ms` while `enabled` (and the tab is visible). */
export function usePolling(fn: () => void | Promise<void>, ms: number, enabled: boolean) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => { if (document.visibilityState === "visible") void ref.current(); }, ms);
    return () => clearInterval(id);
  }, [ms, enabled]);
}
