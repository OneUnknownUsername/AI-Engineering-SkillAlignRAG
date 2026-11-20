import { useState } from 'react';
import { api } from '../api.js';
import { ThemeToggle } from './ui.jsx';

// Accounts are created by an administrator; there is no self-registration.
export default function SignIn({ onSignedIn }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onSignedIn(await api('/api/sign-in', { method: 'POST', body: JSON.stringify({ username, password }) }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="signin">
      <ThemeToggle className="signin-theme" />
      <form onSubmit={submit} className="card">
        <div className="card-header">
          <h1 className="card-title">SkillAlignRAG</h1>
        </div>
        <div className="card-content form">
          <label className="field">
            <span>Username</span>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus />
          </label>
          <label className="field">
            <span>Password</span>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <div className="alert alert-danger" role="alert">{error}</div>}
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </div>
      </form>
    </div>
  );
}
