import { STATUS_INFO } from '../api.js';

// A cell result. Its meaning (and `detail`, such as why evidence is insufficient) is in the tooltip.
export default function StatusBadge({ status, onClick, label, detail }) {
  const info = STATUS_INFO[status] || { tone: 'neutral', text: status };
  const title = detail ? `${info.text} ${detail}` : info.text;
  const className = `badge badge-${info.tone}`;
  if (!onClick) return <span className={className} title={title}>{status}</span>;
  return <button className={className} onClick={onClick} title={title} aria-label={label}>{status}</button>;
}
