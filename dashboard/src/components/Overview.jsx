import { useState } from 'react';
import { cellLabel, LEVELS } from '../api.js';
import useApi, { usePolling } from '../useApi.js';
import LoadError from './LoadError.jsx';
import { overviewColumns } from '../extensions.js';
import { Badge, PageHeader } from './ui.jsx';
import StatusBadge from './StatusBadge.jsx';
import EvidenceDrawer from './EvidenceDrawer.jsx';
import UploadDialog from './UploadDialog.jsx';

export default function Overview({ title, user, workspace, onSignedOut }) {
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
  const columns = 2 + LEVELS.length + overviewColumns.length;

  return (
    <section>
      <PageHeader title={title}>
        {updating.length > 0 && <span role="status"><Badge tone="info">Updating {updating.join(', ')}…</Badge></span>}
        {workspace && <button className="btn btn-primary" onClick={() => setUploading(true)}>Upload</button>}
      </PageHeader>

      <div className="toolbar">
        <select className="select select-sm" aria-label="Course" value={course} onChange={(e) => setCourse(e.target.value)}>
          <option value="">All courses</option>
          {courses.map((c) => <option key={c.course_code} value={c.course_code}>{c.course_code} — {c.course_title}</option>)}
        </select>
        <select className="select select-sm" aria-label="Skill" value={skill} onChange={(e) => setSkill(e.target.value)}>
          <option value="">All skills</option>
          {skills.map((s) => <option key={s.skill_id} value={s.skill_id}>{s.skill_id} — {s.skill_name}</option>)}
        </select>
        {(course || skill) && <button className="btn btn-ghost btn-sm" onClick={() => { setCourse(''); setSkill(''); }}>Reset</button>}
      </div>

      {error && <LoadError message={error} onRetry={retry} />}
      {!rows ? !error && <p className="loading">Loading…</p> : (
        <>
          <div className="table-container">
            <table className="table matrix">
              <thead>
                <tr>
                  <th>Course</th><th>Skill</th>
                  {LEVELS.map((l) => <th key={l} className="level">{l}</th>)}
                  {overviewColumns.map((c) => <th key={c.key}>{c.header}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && <tr className="empty"><td colSpan={columns}>No results.</td></tr>}
                {rows.map((row) => (
                  <tr key={`${row.course_code}-${row.skill_id}`}>
                    <td><span className="font-medium">{row.course_code}</span> <span className="text-muted">{row.course_title}</span></td>
                    <td><span className="font-medium">{row.skill_id}</span> {row.skill_name}</td>
                    {LEVELS.map((level) => {
                      const cell = row.levels[level];
                      return (
                        <td key={level} className="level">
                          {cell ? (
                            <StatusBadge
                              status={cellLabel(cell)}
                              label={`${row.course_code} ${row.skill_id} ${level}: ${cellLabel(cell)}`}
                              detail={cell.state === 'complete' && cell.status === 'Insufficient Evidence' ? cell.reason : null}
                              onClick={() => setOpen({ course: row.course_code, skill: row.skill_id, level })}
                            />
                          ) : <span className="text-muted">—</span>}
                        </td>
                      );
                    })}
                    {overviewColumns.map((c) => <td key={c.key}>{c.render(row)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="table-footer">{rows.length} rows · {rows.length * LEVELS.length} cells</p>
        </>
      )}
      {open && <EvidenceDrawer {...open} onClose={() => setOpen(null)} onSignedOut={onSignedOut} />}
      {uploading && (
        <UploadDialog user={user} courses={courses} onClose={() => setUploading(false)} onSubmitted={refresh} onSignedOut={onSignedOut} />
      )}
    </section>
  );
}
