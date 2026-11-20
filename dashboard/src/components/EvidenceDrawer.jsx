import { useEffect, useState } from 'react';
import useApi from '../useApi.js';
import LoadError from './LoadError.jsx';
import { drawerSections } from '../extensions.js';
import StatusBadge from './StatusBadge.jsx';
import CiComparison from './CiComparison.jsx';
import CitationChip from './CitationChip.jsx';
import SourcePanel from './SourcePanel.jsx';

export default function EvidenceDrawer({ course, skill, level, onClose, onSignedOut }) {
  const { data: detail, error, retry } = useApi(`/api/cells/${course}/${skill}/${level}`, onSignedOut);
  const [source, setSource] = useState(null); // which cited source the left panel shows: 'citation' or 'corroboration-N'

  useEffect(() => setSource(null), [course, skill, level]);

  // Esc closes the source panel first, then the drawer.
  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== 'Escape') return;
      if (source) setSource(null);
      else onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, source]);

  const chip = (item, sourceFile, page) => (
    <CitationChip course={course} skill={skill} level={level} item={item} sourceFile={sourceFile} page={page}
      onOpenSource={setSource} onSignedOut={onSignedOut} />
  );

  return (
    <>
    {source && <SourcePanel course={course} skill={skill} level={level} item={source} onClose={() => setSource(null)} onSignedOut={onSignedOut} />}
    <aside className="drawer" role="dialog" aria-label="Evidence">
      <div className="drawer-head">
        <div>
          <div className="muted small">{course} · {level}</div>
          <h2>{skill} {detail?.skill_name}</h2>
        </div>
        <button className="link" onClick={onClose} aria-label="Close">Close ✕</button>
      </div>
      {error && <LoadError message={error} onRetry={retry} />}
      {!detail ? !error && <p className="loading">Loading…</p> : (
        <div className="drawer-body">
          <p className="muted">{detail.skill_description}</p>
          <p><StatusBadge status={detail.status} /></p>
          {detail.reason && <p>{detail.reason}</p>}
          {detail.note && <p className="muted">{detail.note}</p>}

          {detail.citation && (
            <div className="evidence">
              <h3>Verified evidence</h3>
              <blockquote>“{detail.citation.quote}”</blockquote>
              <dl>
                <dt>File</dt><dd><code>{detail.citation.source_file}</code></dd>
                <dt>Page or slide</dt><dd>{chip('citation', detail.citation.source_file, detail.citation.page_or_slide)}</dd>
                {detail.nli?.entailment != null && (<>
                  <dt>NLI entailment</dt>
                  <dd>{(detail.nli.entailment * 100).toFixed(1)}% that the quote supports “{detail.nli.hypothesis}”</dd>
                </>)}
              </dl>
              <p className="muted small">The quote was matched word for word on this page and checked by the NLI verifier. Hover over the page or slide to see it in context.</p>
            </div>
          )}

          {detail.corroboration.length > 0 && (
            <div className="evidence">
              <h3>Corroboration from lecture slides</h3>
              <p className="muted small">These slides repeat the cited Course Information wording. They corroborate it; the CLO result rests on the Course Information document.</p>
              <ul>
                {detail.corroboration.map((s, i) => (
                  <li key={`${s.doc_id}-${s.page_or_slide}`}>
                    <code>{s.source_file}</code>, {chip(`corroboration-${i}`, s.source_file, s.page_or_slide)}
                    {s.quote && <div className="muted small">“{s.quote}”</div>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {detail.level === 'CLO' && detail.ci_comparison && <CiComparison comparison={detail.ci_comparison} />}
          {drawerSections.map((render, i) => <div key={i}>{render(detail)}</div>)}
        </div>
      )}
    </aside>
    </>
  );
}
