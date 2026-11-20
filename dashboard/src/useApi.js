import { useEffect, useState } from 'react';
import { api, isCancelled } from './api.js';

// Loads `path` and reloads it whenever `path` changes. A request that is no longer needed is
// cancelled, so a slow answer for an earlier path can never replace the current one.
// Returns { data, error, retry }; data is null while loading. A 401 calls onSignedOut.
export default function useApi(path, onSignedOut) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!path) return undefined;
    const controller = new AbortController();
    setData(null);
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

  return { data, error, retry: () => setAttempt((n) => n + 1) };
}
