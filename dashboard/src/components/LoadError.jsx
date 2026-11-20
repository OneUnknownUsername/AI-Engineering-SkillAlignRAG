// An error message with a button to try the request again.
export default function LoadError({ message, onRetry }) {
  return (
    <div className="alert alert-danger" role="alert">
      <span>{message}</span>
      {onRetry && <button className="btn btn-outline btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}
