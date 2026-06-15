import { useCallback, useEffect, useRef, useState } from "react";

import type { IpcResult } from "../../../shared/ipc-contract";

export const api = window.skillctl;

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useAsync<T>(fn: () => Promise<IpcResult<T>>): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(() => {
    setLoading(true);
    setError(null);
    fnRef
      .current()
      .then((res) => {
        if (res.ok) {
          setData(res.data);
        } else {
          setError(res.error);
        }
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    run();
  }, [run]);

  return { data, error, loading, reload: run };
}
