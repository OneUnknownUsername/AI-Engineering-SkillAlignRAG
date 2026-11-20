import { useEffect, useRef } from 'react';

// A pop-up window in the centre of the screen. Esc, the close button or a click outside closes it.
export default function Modal({ title, onClose, children }) {
  const box = useRef(null);

  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    box.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={box}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="link" onClick={onClose} aria-label="Close">Close ✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
