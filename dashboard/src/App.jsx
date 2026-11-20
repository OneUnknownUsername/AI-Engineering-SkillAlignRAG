import { useEffect, useState } from 'react';
import { api } from './api.js';
import { pages as extensionPages } from './extensions.js';
import SignIn from './components/SignIn.jsx';
import Overview from './components/Overview.jsx';
import SkillsPage from './components/SkillsPage.jsx';
import CoursesPage from './components/CoursesPage.jsx';

const PAGES = [
  { key: 'overview', label: 'Coverage overview', render: (props) => <Overview {...props} /> },
  { key: 'skills', label: 'Industry skills', render: (props) => <SkillsPage {...props} /> },
  { key: 'courses', label: 'Courses', render: (props) => <CoursesPage {...props} /> },
  ...extensionPages,
];

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

  if (user === undefined) return <p className="loading">Loading…</p>;
  if (!user) return <SignIn onSignedIn={setUser} />;

  // A request that comes back 401 (session ended) returns the user to sign-in.
  const onSignedOut = () => setUser(null);
  const pages = PAGES;
  const current = pages.find((p) => p.key === page) || pages[0];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>SkillAlignRAG</strong>
          <span>Industry skill coverage across CLO, Taught and Assessed evidence</span>
        </div>
        <nav aria-label="Pages">
          {pages.map((p) => (
            <button key={p.key} className={p.key === current.key ? 'tab active' : 'tab'} onClick={() => setPage(p.key)}>
              {p.label}
            </button>
          ))}
        </nav>
        <div className="account">
          <span title={user.roles.join(', ') || 'no roles'}>
            {user.username}
            {user.can_upload ? ' · approved staff' : ''}
          </span>
          <button className="link" onClick={signOut}>Sign out</button>
        </div>
      </header>
      {run && (
        <p className="run-info">
          {run.workspace
            ? <>Dashboard workspace, started from <code>{run.workspace.started_from}</code>; {run.workspace.uploads_processed} upload{run.workspace.uploads_processed === 1 ? '' : 's'} processed since</>
            : <>Showing saved run <code>{run.run_folder}</code> (read-only)</>}
          {run.commit && <> · code <code>{run.commit.slice(0, 7)}</code>{run.uncommitted_code_changes && ' (uncommitted changes)'}</>}
          {run.gpu && <> · {run.gpu}</>}
        </p>
      )}
      {/* workspace is null when a saved run is shown read-only; uploads then do not exist. */}
      <main>{current.render({ user, workspace: run?.workspace || null, onSignedOut })}</main>
    </div>
  );
}
