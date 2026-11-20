// Small shared building blocks, modelled on shadcn/ui (Badge, page header, theme toggle, sheet and
// dialog close button). Styles live in styles.css under the same names.
import { useState } from 'react';
import { currentTheme, setTheme } from '../theme.js';

// tone: supported | neutral | warning | danger | info | outline
export function Badge({ tone = 'neutral', title, children }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

// "processed" -> "Processed", for labels that come from the API in lower case.
export const capitalize = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text);

export function PageHeader({ title, children }) {
  return (
    <div className="page-header">
      <h1>{title}</h1>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

// Switches between dark and light mode; shows the mode it switches to.
export function ThemeToggle({ className = '' }) {
  const [theme, setThemeState] = useState(currentTheme);
  const next = theme === 'dark' ? 'light' : 'dark';
  const label = `Switch to ${next} mode`;
  return (
    <button className={`btn btn-ghost btn-icon ${className}`} onClick={() => { setTheme(next); setThemeState(next); }} aria-label={label} title={label}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {next === 'light' ? (
          <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2m-7.07-17.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></>
        ) : (
          <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
        )}
      </svg>
    </button>
  );
}

export function CloseButton({ onClick, label = 'Close', className = '' }) {
  return (
    <button className={`btn btn-ghost btn-icon ${className}`} onClick={onClick} aria-label={label} title={label}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M18 6 6 18" /><path d="m6 6 12 12" />
      </svg>
    </button>
  );
}
