import { Badge } from './ui.jsx';

const STATUS = {
  repeats_ci: { label: 'Repeats the CI', tone: 'supported' },
  differs_from_ci: { label: 'Differs from the CI', tone: 'warning' },
  not_in_ci: { label: 'Not in the CI', tone: 'warning' },
  no_ci: { label: 'No CI to compare with', tone: 'neutral' },
};

// Lecture slides that state learning outcomes, compared with the Course Information (CI) document.
// The CI alone decides CLO coverage (FR3); slides can only corroborate it, so without a usable CI
// every CLO cell is Insufficient Evidence.
export default function CiComparison({ comparison }) {
  const pages = comparison.slide_pages || [];
  return (
    <div className="section">
      <h3 className="section-title">Slides that state learning outcomes</h3>
      <div className="stack">
        {!comparison.ci_available && <p className="text-warning">No usable Course Information document.</p>}
        {pages.length === 0 ? <p className="text-muted">None.</p> : (
          <ul className="list">
            {pages.map((page) => (
              <li key={`${page.doc_id}-${page.pdf_page_no}`}>
                <div className="text-muted"><code>{page.doc_id}</code>, page {page.pdf_page_no}</div>
                <ul className="badged-list">
                  {page.statements.map((s, i) => {
                    const status = STATUS[s.status] || { label: s.status, tone: 'neutral' };
                    return (
                      <li key={i}>
                        <Badge tone={status.tone}>{status.label}</Badge>
                        <div>{s.statement}</div>
                        {s.status === 'differs_from_ci' && s.ci_statement && (
                          <div className="text-muted note">
                            CI {s.ci_clo} (<code>{s.ci_doc_id}</code>, page {s.ci_pdf_page_no}): {s.ci_statement}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
