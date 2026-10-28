"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/** Cancels obsolete requests when a page leaves or its resource changes. */
export function useApiQuery<T>(path: string | null, authenticated = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(path));
  const controller = useRef<AbortController | null>(null);

  const reload = useCallback(async () => {
    controller.current?.abort();
    if (!path) {
      setData(null);
      setError("");
      setLoading(false);
      return;
    }
    const current = new AbortController();
    controller.current = current;
    setError("");
    setLoading(true);
    try {
      const result = await api<T>(path, { signal: current.signal }, authenticated);
      if (!current.signal.aborted) setData(result);
    } catch (reason) {
      if (!current.signal.aborted) {
        setError(reason instanceof Error ? reason.message : "Không thể tải dữ liệu.");
      }
    } finally {
      if (!current.signal.aborted) setLoading(false);
    }
  }, [path, authenticated]);

  useEffect(() => {
    setData(null);
    void reload();
    return () => controller.current?.abort();
  }, [reload]);

  return { data, error, loading, reload };
}
