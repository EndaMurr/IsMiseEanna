import { useEffect, useState } from "react";
import type { DependencyList } from "react";

interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
}

/**
 * Runs `fn` on mount and whenever `deps` change; pass `null` for `fn` to skip
 * fetching (e.g. while a required input like a race date is still empty).
 */
export function useAsync<T>(fn: (() => Promise<T>) | null, deps: DependencyList): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: fn !== null });

  // oxlint-disable-next-line react-hooks/exhaustive-deps -- deps is an intentionally caller-provided dependency list
  useEffect(() => {
    if (!fn) {
      setState({ data: null, error: null, loading: false });
      return;
    }

    let cancelled = false;
    setState({ data: null, error: null, loading: true });

    fn()
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ data: null, error, loading: false });
      });

    return () => {
      cancelled = true;
    };
  }, deps);

  return state;
}
