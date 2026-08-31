import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '@/api/client';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** True while a background refresh is running and we already have data. */
  refreshing: boolean;
  reload: () => void;
  setData: (next: T) => void;
}

/**
 * Small data-fetching primitive with loading / error / retry semantics and
 * stale-response protection. `fn` must be stable across renders or wrapped in
 * useCallback by the caller; `deps` controls when it re-runs.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const runId = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    const id = ++runId.current;
    let cancelled = false;

    setLoading(true);
    setError(null);

    fnRef
      .current()
      .then((result) => {
        if (cancelled || id !== runId.current) return;
        setData(result);
      })
      .catch((err: unknown) => {
        if (cancelled || id !== runId.current) return;
        setError(
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : 'Unexpected error while loading data.',
        );
      })
      .finally(() => {
        if (cancelled || id !== runId.current) return;
        setLoading(false);
        setRefreshing(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => {
    setRefreshing(true);
    setNonce((n) => n + 1);
  }, []);

  const setLocal = useCallback((next: T) => setData(next), []);

  return { data, loading, error, refreshing, reload, setData: setLocal };
}
