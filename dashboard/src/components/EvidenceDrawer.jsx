import { useEffect, useState } from 'react';
import { cellLabel } from '../api.js';
import useApi, { usePolling } from '../useApi.js';
import LoadError from './LoadError.jsx';
import { drawerSections } from '../extensions.js';
import { CloseButton } from './ui.jsx';
import StatusBadge from './StatusBadge.jsx';
import CiComparison from './CiComparison.jsx';
import CitationChip from './CitationChip.jsx';
import SourcePanel from './SourcePanel.jsx';

// One cell's evidence. A verified citation was matched word for word on its page and checked by the
// NLI verifier. Corroborating slides repeat the cited Course Information wording; the CLO result
// rests on the Course Information document alone.
export default function EvidenceDrawer({ course, skill, level, onClose, onSignedOut }) {
  const { data: detail, error, retry, refresh } = useApi(`/api/cells/${course}/${skill}/${level}`, onSignedOut);
  usePolling(detail?.state === 'pending' || detail?.state === 'processing', refresh);
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
    <aside className="sheet sheet-right" role="dialog" aria-label="Evidence">
      <div className="sheet-header">
        <div>
          <h2 className="sheet-title">{skill} {detail?.skill_name}</h2>
          <p className="sheet-description">{course} · {level}</p>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="sheet-body">
        {error && <LoadError message={error} onRetry={retry} />}
        {!detail ? !error && <p className="loading">Loading…</p> : (
          <>
            <p className="text-muted">{detail.skill_description}</p>
            <div className="inline">
              <StatusBadge status={cellLabel(detail)} />
              {detail.updated_by && <span className="text-muted text-xs">Re-audited after upload {detail.updated_by}</span>}
            </div>
            {detail.reason && <p>{detail.reason}</p>}
            {detail.note && <p className="text-muted">{detail.note}</p>}

            {detail.citation && (
              <div className="section">
                <h3 className="section-title">Verified evidence</h3>
                <div className="stack">
                  <blockquote className="quote">“{detail.citation.quote}”</blockquote>
                  <dl className="kv">
                    <dt>File</dt><dd><code>{detail.citation.source_file}</code></dd>
                    <dt>Page or slide</dt><dd>{chip('citation', detail.citation.source_file, detail.citation.page_or_slide)}</dd>
                    {detail.nli?.entailment != null && (<>
                      <dt>NLI hypothesis</dt><dd>“{detail.nli.hypothesis}”</dd>
                      <dt>Entailment</dt><dd>{(detail.nli.entailment * 100).toFixed(1)}%</dd>
                    </>)}
                  </dl>
                </div>
              </div>
            )}

            {detail.corroboration.length > 0 && (
              <div className="section">
                <h3 className="section-title">Corroborating lecture slides</h3>
                <ul className="list">
                  {detail.corroboration.map((s, i) => (
                    <li key={`${s.doc_id}-${s.page_or_slide}`}>
                      <div><code>{s.source_file}</code> {chip(`corroboration-${i}`, s.source_file, s.page_or_slide)}</div>
                      {s.quote && <div className="text-muted">“{s.quote}”</div>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.level === 'CLO' && detail.ci_comparison && <CiComparison comparison={detail.ci_comparison} />}
            {drawerSections.map((render, i) => <div key={i}>{render(detail)}</div>)}
          </>
        )}
      </div>
    </aside>
    </>
  );
}
