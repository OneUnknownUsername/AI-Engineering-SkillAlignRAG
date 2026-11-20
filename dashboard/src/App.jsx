import { useEffect, useState } from 'react';
import { api } from './api.js';
import { pages as extensionPages } from './extensions.js';
import { Badge, ThemeToggle } from './components/ui.jsx';
import SignIn from './components/SignIn.jsx';
import Overview from './components/Overview.jsx';
import SkillsPage from './components/SkillsPage.jsx';
import CoursesPage from './components/CoursesPage.jsx';

const PAGES = [
  { key: 'overview', label: 'Coverage Overview', render: (props) => <Overview {...props} /> },
  { key: 'skills', label: 'Industry Skills', render: (props) => <SkillsPage {...props} /> },
  { key: 'courses', label: 'Courses', render: (props) => <CoursesPage {...props} /> },
  ...extensionPages,
];

// Which results are on screen and which code produced them, shown in the footer.
function RunInfo({ run }) {
  const parts = [];
  if (run.workspace) {
    const n = run.workspace.uploads_processed;
    parts.push(<>Workspace from <code>{run.workspace.started_from}</code></>, `${n} upload${n === 1 ? '' : 's'} processed`);
  } else {
    parts.push(<>Saved run <code>{run.run_folder}</code> (read-only)</>);
  }
  if (run.commit) parts.push(<>Code <code>{run.commit.slice(0, 7)}</code>{run.uncommitted_code_changes && ' (uncommitted changes)'}</>);
  if (run.gpu) parts.push(run.gpu);
  return parts.map((part, i) => <span key={i}>{i > 0 && ' · '}{part}</span>);
}

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = still checking the session
  const [run, setRun] = useState(null);
  const [page, setPage] = useState('overview');

  useEffect(() => {
    api('/api/me').then(setUser).catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (user) api('/api/run').then(setRun).catch(() => setRun(null));
  }, [user]);

  async function signOut() {
    await api('/api/sign-out', { method: 'POST' }).catch(() => {});
    setUser(null);
  }

  if (user === undefined) return <p className="loading container">Loading…</p>;
  if (!user) return <SignIn onSignedIn={setUser} />;

  // A request that comes back 401 (session ended) returns the user to sign-in.
  const onSignedOut = () => setUser(null);
  const pages = PAGES;
  const current = pages.find((p) => p.key === page) || pages[0];

  return (
    <div className="app">
      <header className="site-header">
        <div className="container">
          <span className="brand">SkillAlignRAG</span>
          <span className="header-separator" aria-hidden="true" />
          <nav className="main-nav" aria-label="Pages">
            {pages.map((p) => (
              <button key={p.key} aria-current={p.key === current.key ? 'page' : undefined} onClick={() => setPage(p.key)}>
                {p.label}
              </button>
            ))}
          </nav>
          <div className="account">
            <span title={user.roles.join(', ') || 'no roles'}>{user.username}</span>
            {user.can_upload && <Badge tone="outline">Approved staff</Badge>}
            <button className="btn btn-ghost btn-sm" onClick={signOut}>Sign out</button>
            <ThemeToggle />
          </div>
        </div>
      </header>
      {/* workspace is null when a saved run is shown read-only; uploads then do not exist. */}
      <main className="container">{current.render({ title: current.label, user, workspace: run?.workspace || null, onSignedOut })}</main>
      {run && (
        <footer className="site-footer">
          <div className="container"><RunInfo run={run} /></div>
        </footer>
      )}
    </div>
  );
}
