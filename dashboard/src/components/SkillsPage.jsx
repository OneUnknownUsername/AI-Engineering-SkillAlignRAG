import useApi from '../useApi.js';
import LoadError from './LoadError.jsx';

// FR7: the predefined benchmark is shown without any upload or setup.
export default function SkillsPage({ onSignedOut }) {
  const { data: skills, error, retry } = useApi('/api/skills', onSignedOut);

  if (error) return <LoadError message={error} onRetry={retry} />;
  if (!skills) return <p className="loading">Loading…</p>;
  return (
    <section>
      <p className="muted">
        The {skills.length} benchmark skills, curated from the HRD Corp Industrial Skills Framework (IndSF) documents for
        Artificial Intelligence and Data Science. Source passages are matched automatically; a match is a reference, not a certification.
      </p>
      <div className="skill-list">
        {skills.map((s) => (
          <article key={s.skill_id} className="card">
            <h3>{s.skill_id} — {s.skill_name}</h3>
            <p>{s.description}</p>
            <p className="muted small">{s.bucket}{s.sfia_codes.length > 0 && <> · SFIA {s.sfia_codes.join(', ')}</>}</p>
            {s.sources.length === 0 ? (
              <p className="warning-text small">No IndSF source passage scored above the matching threshold.</p>
            ) : (
              <details>
                <summary>IndSF source references ({s.sources.length})</summary>
                <ul>
                  {s.sources.map((src, i) => (
                    <li key={i}>
                      <code>{src.document}</code>, page {src.page}{src.role && <> · {src.role}</>}
                      <div className="muted small">“{src.excerpt}”</div>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
