import { STATUS_INFO } from '../api.js';

export default function StatusBadge({ status, onClick, label }) {
  const info = STATUS_INFO[status] || { tone: 'neutral', text: status };
  const content = <span className={`badge ${info.tone}`}>{status}</span>;
  if (!onClick) return content;
  return (
    <button className="badge-button" onClick={onClick} title={`${info.text} Click to inspect.`} aria-label={label}>
      {content}
    </button>
  );
}
