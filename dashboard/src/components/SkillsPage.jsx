import useApi from '../useApi.js';
import LoadError from './LoadError.jsx';
import { PageHeader } from './ui.jsx';

// FR7: the predefined benchmark, curated from the HRD Corp IndSF documents for AI and Data Science,
// is shown without any upload or setup. A matched source passage is a reference, not a certification.
export default function SkillsPage({ title, onSignedOut }) {
  const { data: skills, error, retry } = useApi('/api/skills', onSignedOut);

  return (
    <section>
      <PageHeader title={title} />
      {error && <LoadError message={error} onRetry={retry} />}
      {!skills ? !error && <p className="loading">Loading…</p> : (
        <div className="card-grid">
          {skills.map((s) => (
            <article key={s.skill_id} className="card">
              <div className="card-header">
                <h2 className="card-title">{s.skill_id} {s.skill_name}</h2>
                <p className="card-description">{s.bucket}{s.sfia_codes.length > 0 && <> · SFIA {s.sfia_codes.join(', ')}</>}</p>
              </div>
              <div className="card-content">
                <p>{s.description}</p>
                {s.sources.length === 0 ? (
                  <p className="text-warning">No IndSF source passage scored above the matching threshold.</p>
                ) : (
                  <details className="disclosure">
                    <summary>IndSF sources ({s.sources.length})</summary>
                    <ul className="list">
                      {s.sources.map((src, i) => (
                        <li key={i}>
                          <div><code>{src.document}</code>, page {src.page}{src.role && <span className="text-muted"> · {src.role}</span>}</div>
                          <div className="text-muted">“{src.excerpt}”</div>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
