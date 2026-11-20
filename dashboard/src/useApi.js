import { useEffect, useRef, useState } from 'react';
import { api, isCancelled } from './api.js';

// Loads `path` and reloads it whenever `path` changes. A request that is no longer needed is
// cancelled, so a slow answer for an earlier path can never replace the current one.
// Returns { data, error, retry, refresh }: retry starts over (showing Loading), refresh fetches
// again quietly, keeping what is on screen until the new answer arrives. A 401 calls onSignedOut.
export default function useApi(path, onSignedOut) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const quiet = useRef(false);

  useEffect(() => {
    if (!path) return undefined;
    const controller = new AbortController();
    if (!quiet.current) setData(null);
    quiet.current = false;
    setError('');
    api(path, { signal: controller.signal })
      .then(setData)
      .catch((err) => {
        if (isCancelled(err)) return;
        if (err.status === 401) onSignedOut?.();
        else setError(err.message);
      });
    return () => controller.abort();
  }, [path, attempt]);

  return {
    data,
    error,
    retry: () => setAttempt((n) => n + 1),
    refresh: () => { quiet.current = true; setAttempt((n) => n + 1); },
  };
}

// Calls `refresh` every `ms` while `active` is true (for example while uploads are processing).
export function usePolling(active, refresh, ms = 4000) {
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(refresh, ms);
    return () => clearInterval(timer);
  }, [active, ms]);
}
