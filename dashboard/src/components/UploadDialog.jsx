import { useState } from 'react';
import { api } from '../api.js';
import useApi, { usePolling } from '../useApi.js';
import LoadError from './LoadError.jsx';
import Modal from './Modal.jsx';
import { Badge, capitalize } from './ui.jsx';

export const CATEGORIES = [
  { level: 'CLO', label: 'Course Information document (CLO)' },
  { level: 'Taught', label: 'Lecture slides (Taught)' },
  { level: 'Assessed', label: 'Assessments and rubrics (Assessed)' },
];
const ACCEPTED = ['.pdf', '.pptx', '.docx'];
const OUTCOME_TONE = { processed: 'supported', queued: 'info', rejected: 'danger', failed: 'danger' };
const JOB_TONE = { queued: 'info', processing: 'info', completed: 'supported', failed: 'danger' };

const extension = (name) => (name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
const when = (iso) => (iso ? new Date(iso).toLocaleString() : '');

function UploadForm({ courses, onSubmitted, onSignedOut }) {
  const [course, setCourse] = useState('');
  const [level, setLevel] = useState('');
  const [files, setFiles] = useState([]);
  const [declared, setDeclared] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [submitted, setSubmitted] = useState(null);

  const unsupported = files.filter((f) => !ACCEPTED.includes(extension(f.name)));
  const ready = course && level && files.length > unsupported.length && declared && !busy;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSubmitted(null);
    const form = new FormData();
    form.append('course', course);
    form.append('level', level);
    form.append('declaration', declared ? 'true' : '');
    files.forEach((file) => form.append('files', file));
    try {
      const job = await api('/api/uploads', { method: 'POST', body: form });
      setSubmitted(job);
      setFiles([]);
      setDeclared(false);
      event.target.reset();
      onSubmitted();
    } catch (err) {
      if (err.status === 401) onSignedOut();
      else setError({ message: err.message, files: err.files || [] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="form-row">
        <label className="field">
          <span>Course</span>
          <select className="select" value={course} onChange={(e) => setCourse(e.target.value)} required>
            <option value="">Choose a course</option>
            {courses.map((c) => <option key={c.course_code} value={c.course_code}>{c.course_code} — {c.course_title}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Category</span>
          <select className="select" value={level} onChange={(e) => setLevel(e.target.value)} required>
            <option value="">Choose a category</option>
            {CATEGORIES.map((c) => <option key={c.level} value={c.level}>{c.label}</option>)}
          </select>
        </label>
      </div>
      <label className="field">
        <span>Files</span>
        <input className="input" type="file" multiple accept={ACCEPTED.join(',')} onChange={(e) => setFiles([...e.target.files])} />
      </label>
      {unsupported.length > 0 && (
        <div className="alert alert-warning" role="alert">
          {unsupported.map((f) => f.name).join(', ')}: unsupported format, so {unsupported.length === 1 ? 'it' : 'they'} will
          not be uploaded. Accepted formats: PDF, PPTX or DOCX.
        </div>
      )}
      <label className="checkbox-field">
        <input type="checkbox" checked={declared} onChange={(e) => setDeclared(e.target.checked)} />
        I confirm these files are approved course materials and contain no student submissions.
      </label>
      {error && (
        <div className="alert alert-danger" role="alert">
          <span>{error.message}</span>
          {error.files.length > 0 && <ul>{error.files.map((f) => <li key={f.name}><strong>{f.name}</strong>: {f.reason}</li>)}</ul>}
        </div>
      )}
      {submitted && (
        <div className="alert alert-success" role="status">
          Submitted. The {submitted.course} {submitted.level} cells will be re-audited in about a minute; you can close
          this window and watch them update.
        </div>
      )}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={!ready}>{busy ? 'Uploading…' : 'Submit'}</button>
      </div>
    </form>
  );
}

function Jobs({ jobs }) {
  if (jobs.length === 0) return <p className="text-muted">No uploads yet.</p>;
  return (
    <ul className="job-list">
      {jobs.map((job) => (
        <li key={job.id} className="job">
          <div className="job-head">
            <Badge tone={JOB_TONE[job.state]}>{capitalize(job.state)}</Badge>
            <span className="font-medium">{job.course} · {job.level}</span>
            <span className="text-muted text-xs">{job.stage} · by {job.user} · {when(job.created_at)}</span>
          </div>
          <ul className="job-files">
            {job.files.map((f) => (
              <li key={f.name}>
                <Badge tone={OUTCOME_TONE[f.outcome] || 'neutral'}>{capitalize(f.outcome)}</Badge>
                <span>{f.name}</span>
                {f.replaced && <span className="text-muted text-xs">Replaced the earlier file</span>}
                {f.pages && <span className="text-muted text-xs">{f.pages} pages</span>}
                {f.reason && <span className="text-muted text-xs reason">{f.reason}</span>}
              </li>
            ))}
          </ul>
          {job.index_update && (
            <p className="text-muted text-xs job-detail">
              Index: {job.index_update.stores_rebuilt.length} of {job.index_update.stores_total} stores rebuilt
              ({job.index_update.stores_rebuilt.join(', ') || 'none changed'}), {job.index_update.vectors_computed} page vectors computed.
              {job.timings && <> Reading {job.timings.reading} s, indexing {job.timings.indexing} s{job.timings.re_auditing != null && <>, re-auditing {job.timings.re_auditing} s</>}.</>}
            </p>
          )}
          {job.error && <p className="text-danger job-detail">{job.error}</p>}
        </li>
      ))}
    </ul>
  );
}

// FR1 and FR6: approved staff upload course files by category; other accounts are told access is denied.
export default function UploadDialog({ user, courses, onClose, onSubmitted, onSignedOut }) {
  const jobs = useApi('/api/uploads', onSignedOut);
  const busy = (jobs.data || []).some((j) => j.state === 'queued' || j.state === 'processing');
  usePolling(busy, jobs.refresh, 3000);

  return (
    <Modal title="Upload course files" description="A file with the same name as an existing one replaces it." onClose={onClose}>
      {user.can_upload ? (
        <UploadForm courses={courses} onSubmitted={() => { jobs.refresh(); onSubmitted(); }} onSignedOut={onSignedOut} />
      ) : (
        <div className="alert alert-danger" role="alert">
          <span><strong>Access denied.</strong> Only approved academic staff can upload course files.</span>
        </div>
      )}
      <div className="section">
        <h3 className="section-title">Recent uploads</h3>
        {jobs.error ? <LoadError message={jobs.error} onRetry={jobs.retry} /> : jobs.data ? <Jobs jobs={jobs.data} /> : <p className="loading">Loading…</p>}
      </div>
    </Modal>
  );
}

// Processed documents of one course by category, with each file's status (shown on the Courses page).
export function CourseDocuments({ documents }) {
  return (
    <details className="disclosure">
      <summary>Documents ({documents.length})</summary>
      <div className="table-container">
        <table className="table">
          <thead><tr><th>Category</th><th>File</th><th>Pages</th><th>Status</th></tr></thead>
          <tbody>
            {CATEGORIES.map(({ level }) => {
              const docs = documents.filter((d) => d.level === level);
              if (docs.length === 0) return <tr key={level}><td>{level}</td><td colSpan={3} className="text-warning">No documents</td></tr>;
              return docs.map((d) => (
                <tr key={d.file}>
                  <td>{level}</td>
                  <td><code>{d.doc_id}</code></td>
                  <td>{d.pages ?? '—'}</td>
                  <td>{d.status === 'ready'
                    ? <Badge tone="supported">Processed</Badge>
                    : <><Badge tone="danger">Failed</Badge>{d.error && <div className="text-muted text-xs">{d.error}</div>}</>}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}
