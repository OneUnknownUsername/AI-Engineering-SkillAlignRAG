import { useEffect, useRef, useState } from 'react';
import { api, isCancelled } from '../api.js';
import { pageLabel, snippet } from '../sourceText.js';

// A page/slide reference that previews the cited passage on hover, focus or tap,
// with a button that opens the whole cited document's text in the source panel.
export default function CitationChip({ course, skill, level, item, sourceFile, page, onOpenSource, onSignedOut }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const [source, setSource] = useState(null);
  const [error, setError] = useState('');
  const closeTimer = useRef(null);
  const wrapper = useRef(null);
  const button = useRef(null);
  const popover = useRef(null);
  const request = useRef(null); // the request in flight, if any

  // Loads once; after an error, the next hover (or "Try again") loads again.
  function load() {
    if (source || request.current) return;
    setError('');
    const controller = new AbortController();
    request.current = controller;
    api(`/api/cells/${course}/${skill}/${level}/source?item=${encodeURIComponent(item)}`, { signal: controller.signal })
      .then(setSource)
      .catch((err) => {
        if (isCancelled(err)) return;
        if (err.status === 401) onSignedOut();
        else setError(err.message);
      })
      .finally(() => { if (request.current === controller) request.current = null; });
  }

  // Placed against the window (not the scrolling drawer) so it is never clipped, and kept on screen.
  function place() {
    const rect = button.current.getBoundingClientRect();
    const width = Math.min(380, window.innerWidth - 16);
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const below = rect.bottom + 6 + 260 < window.innerHeight;
    setPosition(below ? { left, width, top: rect.bottom + 6 } : { left, width, bottom: window.innerHeight - rect.top + 6 });
  }

  function show() {
    clearTimeout(closeTimer.current);
    load();
    if (!open) place();
    setOpen(true);
  }

  // A short delay lets the pointer move from the chip into the popover.
  function hideSoon() {
    clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpen(false), 200);
  }

  useEffect(() => () => {
    clearTimeout(closeTimer.current);
    request.current?.abort();
  }, []);

  // Scrolling would leave the popover behind its chip, so close it instead.
  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (event?.type === 'scroll' && popover.current?.contains(event.target)) return;
      setOpen(false);
    };
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  const preview = source && snippet(source.text, source.highlight);
  const label = pageLabel(sourceFile, page);

  return (
    <span
      className="citation"
      ref={wrapper}
      onMouseEnter={show}
      onMouseLeave={hideSoon}
      onBlur={(e) => !wrapper.current?.contains(e.relatedTarget) && hideSoon()}
    >
      <button
        className="btn btn-outline btn-xs"
        ref={button}
        onFocus={show}
        onClick={show}
        aria-expanded={open}
        aria-label={`Preview the cited text on ${label}`}
      >
        {label}
      </button>
      {open && (
        <span className="citation-popover" role="tooltip" ref={popover} style={position || undefined} onMouseEnter={show}>
          <span className="text-muted text-xs">{sourceFile}, {label}</span>
          {error && (
            <span className="text-danger">
              {error}{' '}
              <button className="btn btn-link" onClick={load}>Try again</button>
            </span>
          )}
          {!source && !error && <span className="text-muted">Loading…</span>}
          {preview && (
            <span className="popover-text">
              {preview.before}
              {preview.match && <mark>{preview.match}</mark>}
              {preview.after}
            </span>
          )}
          {source && !source.highlight && <span className="text-warning">The quote could not be located on this page.</span>}
          {source && (
            <button className="btn btn-link" onClick={() => { setOpen(false); onOpenSource(item); }}>
              Show source text
            </button>
          )}
        </span>
      )}
    </span>
  );
}
