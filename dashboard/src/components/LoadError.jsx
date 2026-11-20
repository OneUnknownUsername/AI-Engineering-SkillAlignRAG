// An error message with a button to try the request again.
export default function LoadError({ message, onRetry }) {
  return (
    <div className="load-error" role="alert">
      <span className="error">{message}</span>
      {onRetry && <button onClick={onRetry}>Try again</button>}
    </div>
  );
}
