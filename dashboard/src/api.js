// All requests send the session cookie; the backend checks sign-in on every call.
//
// Requests travel through the VS Code tunnel, which now and then drops or stalls one. So each
// request has a time limit, and reading requests (GET) are retried automatically before an
// error is shown. Passing `signal` lets a component cancel a request it no longer needs.
const TIMEOUT_MS = 15000;
const RETRIES = 2;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function isCancelled(err) {
  return err?.name === 'AbortError';
}

export async function api(path, options = {}) {
  const { signal, ...rest } = options;
  const reading = !rest.method || rest.method === 'GET';
  const retries = reading ? RETRIES : 0;
  for (let attempt = 0; ; attempt += 1) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    signal?.addEventListener('abort', cancel, { once: true });
    const timer = setTimeout(cancel, TIMEOUT_MS);
    let response;
    let body;
    try {
      response = await fetch(path, {
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        ...rest,
        signal: controller.signal,
      });
      const text = await response.text();
      body = text ? JSON.parse(text) : {};
    } catch (err) {
      if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
      // A dropped connection, a timeout, or a non-JSON page from the tunnel: try again, then report it.
      if (attempt < retries) {
        await wait(400 * (attempt + 1));
        continue;
      }
      const error = new Error('The dashboard did not respond in time. Check that it is still running and its port is forwarded, then try again.');
      error.status = 0;
      throw error;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
    }
    // 502–504 come from the tunnel, not the dashboard: worth another try.
    if (response.status >= 502 && response.status <= 504 && attempt < retries) {
      await wait(400 * (attempt + 1));
      continue;
    }
    if (!response.ok) {
      const error = new Error(body.detail || `Request failed (${response.status})`);
      error.status = response.status;
      error.outOfScope = Boolean(body.out_of_scope);
      throw error;
    }
    return body;
  }
}

export const LEVELS = ['CLO', 'Taught', 'Assessed'];

export const STATUS_INFO = {
  Supported: { tone: 'supported', text: 'Verified evidence found at this level.' },
  'Not Found': { tone: 'neutral', text: 'Documents were checked, but no accepted evidence was found. Not proof of a gap.' },
  'Insufficient Evidence': { tone: 'warning', text: 'The documents for this level are missing or could not be processed.' },
  'Generation Error': { tone: 'danger', text: "The model's answer could not be read. Manual review is required." },
  Pending: { tone: 'info', text: 'Waiting to be processed.' },
  Processing: { tone: 'info', text: 'Being processed now.' },
};
