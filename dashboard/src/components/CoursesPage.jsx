import { LEVELS } from '../api.js';
import useApi from '../useApi.js';
import LoadError from './LoadError.jsx';
import CiComparison from './CiComparison.jsx';

export default function CoursesPage({ onSignedOut }) {
  const { data: courses, error, retry } = useApi('/api/courses', onSignedOut);

  if (error) return <LoadError message={error} onRetry={retry} />;
  if (!courses) return <p className="loading">Loading…</p>;
  return (
    <section className="skill-list">
      {courses.map((c) => (
        <article key={c.course_code} className="card">
          <h3>{c.course_code} — {c.course_title}</h3>
          <table className="availability">
            <tbody>
              {LEVELS.map((level) => (
                <tr key={level}>
                  <th>{level}</th>
                  <td>{c.availability[level] ? 'Documents available' : <span className="warning-text">Missing or could not be processed</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {c.ci_comparison && <CiComparison comparison={c.ci_comparison} />}
        </article>
      ))}
    </section>
  );
}
