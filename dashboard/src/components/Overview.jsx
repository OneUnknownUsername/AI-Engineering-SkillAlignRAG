import { useState } from 'react';
import { cellLabel, LEVELS, STATUS_INFO } from '../api.js';
import useApi, { usePolling } from '../useApi.js';
import LoadError from './LoadError.jsx';
import { overviewColumns } from '../extensions.js';
import StatusBadge from './StatusBadge.jsx';
import EvidenceDrawer from './EvidenceDrawer.jsx';
import UploadDialog from './UploadDialog.jsx';

const LEGEND = ['Supported', 'Not Found', 'Insufficient Evidence', 'Generation Error'];

export default function Overview({ user, workspace, onSignedOut }) {
  const [course, setCourse] = useState('');
  const [skill, setSkill] = useState('');
  const [open, setOpen] = useState(null);
  const [uploading, setUploading] = useState(false);
  const courses = useApi('/api/courses', onSignedOut).data || [];
  const skills = useApi('/api/skills', onSignedOut).data || [];
  // Filtering reads saved results only; it never runs the models.
  const params = new URLSearchParams();
  if (course) params.set('course', course);
  if (skill) params.set('skill', skill);
  const { data: rows, error, retry, refresh } = useApi(`/api/overview?${params}`, onSignedOut);
  // While uploads are being processed, refresh quietly so cells update without a reload.
  const busy = (rows || []).some((r) => Object.values(r.levels).some((c) => c.state === 'pending' || c.state === 'processing'));
  usePolling(busy, refresh);
  // Course and category being updated by uploads, for the note beside the Upload button.
  const updating = [...new Set((rows || []).flatMap((r) => Object.entries(r.levels)
    .filter(([, c]) => c.state === 'pending' || c.state === 'processing').map(([level]) => `${r.course_code} ${level}`)))];

  return (
    <section>
      <div className="toolbar">
        <label>
          Course
          <select value={course} onChange={(e) => setCourse(e.target.value)}>
            <option value="">All courses</option>
            {courses.map((c) => <option key={c.course_code} value={c.course_code}>{c.course_code} — {c.course_title}</option>)}
          </select>
        </label>
        <label>
          Skill
          <select value={skill} onChange={(e) => setSkill(e.target.value)}>
            <option value="">All skills</option>
            {skills.map((s) => <option key={s.skill_id} value={s.skill_id}>{s.skill_id} — {s.skill_name}</option>)}
          </select>
        </label>
        <button onClick={() => { setCourse(''); setSkill(''); }} disabled={!course && !skill}>Clear filters</button>
        {rows && <span className="muted">{rows.length} course–skill rows · {rows.length * LEVELS.length} cells</span>}
        {workspace && (
          <div className="toolbar-end">
            {updating.length > 0 && <span className="updating" role="status">Updating {updating.join(', ')}…</span>}
            <button className="primary" onClick={() => setUploading(true)}>Upload</button>
          </div>
        )}
      </div>

      <ul className="legend">
        {LEGEND.map((s) => <li key={s}><StatusBadge status={s} /> {STATUS_INFO[s].text}</li>)}
      </ul>

      {error && <LoadError message={error} onRetry={retry} />}
      {!rows ? !error && <p className="loading">Loading…</p> : (
        <div className="table-wrap">
          <table className="matrix">
            <thead>
              <tr>
                <th>Course</th><th>Skill</th>
                {LEVELS.map((l) => <th key={l}>{l}</th>)}
                {overviewColumns.map((c) => <th key={c.key}>{c.header}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.course_code}-${row.skill_id}`}>
                  <td><strong>{row.course_code}</strong><div className="muted small">{row.course_title}</div></td>
                  <td><strong>{row.skill_id}</strong> {row.skill_name}</td>
                  {LEVELS.map((level) => {
                    const cell = row.levels[level];
                    return (
                      <td key={level}>
                        {cell ? (
                          <StatusBadge
                            status={cellLabel(cell)}
                            label={`${row.course_code} ${row.skill_id} ${level}: ${cellLabel(cell)}`}
                            onClick={() => setOpen({ course: row.course_code, skill: row.skill_id, level })}
                          />
                        ) : <span className="muted">—</span>}
                        {cell?.reason && cell.state === 'complete' && cell.status === 'Insufficient Evidence' && <div className="muted small">{cell.reason}</div>}
                      </td>
                    );
                  })}
                  {overviewColumns.map((c) => <td key={c.key}>{c.render(row)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && <EvidenceDrawer {...open} onClose={() => setOpen(null)} onSignedOut={onSignedOut} />}
      {uploading && (
        <UploadDialog user={user} courses={courses} onClose={() => setUploading(false)} onSubmitted={refresh} onSignedOut={onSignedOut} />
      )}
    </section>
  );
}
