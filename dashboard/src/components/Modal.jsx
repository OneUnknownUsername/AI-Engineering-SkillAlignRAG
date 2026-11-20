import { useEffect, useRef } from 'react';
import { CloseButton } from './ui.jsx';

// A pop-up window in the centre of the screen. Esc, the close button or a click outside closes it.
export default function Modal({ title, description, onClose, children }) {
  const box = useRef(null);

  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    box.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="dialog-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={box}>
        <div className="dialog-header">
          <h2 className="dialog-title">{title}</h2>
          {description && <p className="dialog-description">{description}</p>}
        </div>
        <CloseButton onClick={onClose} className="dialog-close" />
        {children}
      </div>
    </div>
  );
}
