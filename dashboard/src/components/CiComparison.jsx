const LABELS = {
  repeats_ci: 'Repeats the CI',
  differs_from_ci: 'Differs from the CI',
  not_in_ci: 'Not in the CI',
  no_ci: 'No CI to compare with',
};

// Lecture slides that state learning outcomes, compared with the Course Information (CI) document.
// The CI alone decides CLO coverage (FR3); slides can only corroborate it.
export default function CiComparison({ comparison }) {
  const pages = comparison.slide_pages || [];
  return (
    <div className="evidence">
      <h3>Slides that state learning outcomes</h3>
      {!comparison.ci_available && (
        <p className="warning-text">This course has no usable Course Information document, so every CLO cell is Insufficient Evidence. Slide statements cannot fill that gap.</p>
      )}
      {pages.length === 0 ? <p className="muted small">No lecture slide states learning outcomes for this course.</p> : (
        <ul className="comparison">
          {pages.map((page) => (
            <li key={`${page.doc_id}-${page.pdf_page_no}`}>
              <div className="muted small"><code>{page.doc_id}</code>, page {page.pdf_page_no}</div>
              <ul>
                {page.statements.map((s, i) => (
                  <li key={i}>
                    <span className={`tag ${s.status}`}>{LABELS[s.status] || s.status}</span> {s.statement}
                    {s.status === 'differs_from_ci' && s.ci_statement && (
                      <div className="muted small">
                        Course Information {s.ci_clo} (<code>{s.ci_doc_id}</code>, page {s.ci_pdf_page_no}): {s.ci_statement}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
