import { useEffect, useRef } from 'react';
import useApi from '../useApi.js';
import LoadError from './LoadError.jsx';
import { pageLabel } from '../sourceText.js';
import { Badge, CloseButton } from './ui.jsx';

// Part of the page text, with the part inside the highlighted quote marked.
// The first mark gets `markRef`, so the panel can scroll the quote into view.
function Fragment({ text, start, end, highlight, markRef, marked }) {
  if (!highlight || highlight[1] <= start || highlight[0] >= end) return text.slice(start, end);
  const from = Math.max(start, highlight[0]);
  const to = Math.min(end, highlight[1]);
  const first = !marked.current;
  marked.current = true;
  return (
    <>
      {text.slice(start, from)}
      <mark ref={first ? markRef : undefined}>{text.slice(from, to)}</mark>
      {text.slice(to, end)}
    </>
  );
}

// Groups consecutive bullet or numbered blocks into one list, and puts OCR text under its own label.
function PageBody({ page, highlight, markRef }) {
  const marked = useRef(false);
  marked.current = false;
  const frag = (b) => <Fragment text={page.text} start={b.start} end={b.end} highlight={highlight} markRef={markRef} marked={marked} />;
  const out = [];
  let list = null;
  let ocrLabelShown = false;
  page.blocks.forEach((block, i) => {
    if (block.ocr && !ocrLabelShown) {
      list = null;
      ocrLabelShown = true;
      out.push(<div key={`ocr-${i}`} className="ocr-label">Text from images (OCR)</div>);
    }
    if (block.kind === 'bullet' || block.kind === 'numbered') {
      if (!list || list.kind !== block.kind) {
        list = { kind: block.kind, items: [] };
        out.push(list);
      }
      list.items.push(<li key={i}>{frag(block)}</li>);
      return;
    }
    list = null;
    const className = block.ocr ? 'block ocr' : 'block';
    if (block.kind === 'title') out.push(<h3 key={i} className="page-title">{frag(block)}</h3>);
    else if (block.kind === 'heading') out.push(<h4 key={i} className="page-heading">{frag(block)}</h4>);
    else out.push(<p key={i} className={className}>{frag(block)}</p>);
  });
  if (!page.text.trim()) return <p className="text-muted">(no text on this page)</p>;
  return out.map((item, i) => (item.items
    ? (item.kind === 'numbered'
      ? <ul key={`list-${i}`} className="numbered-list">{item.items}</ul>
      : <ul key={`list-${i}`}>{item.items}</ul>)
    : item));
}

// The whole extracted text of a cited document, page by page, opened from the left: native text,
// then text read from images, exactly as the citation verifier checked it, laid out from the page's
// line breaks. The cited page is marked and the quote is highlighted and scrolled into view.
export default function SourcePanel({ course, skill, level, item, onClose, onSignedOut }) {
  const { data: doc, error, retry } = useApi(
    `/api/cells/${course}/${skill}/${level}/document?item=${encodeURIComponent(item)}`, onSignedOut);
  const mark = useRef(null);
  const citedPage = useRef(null);

  useEffect(() => {
    (mark.current || citedPage.current)?.scrollIntoView({ block: 'center' });
  }, [doc]);

  const unit = doc && (pageLabel(doc.source_file, 1).startsWith('slide') ? 'slides' : 'pages');

  return (
    <aside className="sheet sheet-left" role="dialog" aria-label="Source text">
      <div className="sheet-header">
        <div>
          <h2 className="sheet-title">{doc ? <code>{doc.source_file}</code> : error ? 'Could not load the source text' : 'Loading…'}</h2>
          {doc && <p className="sheet-description">{doc.pages.length} {unit} · cited on {pageLabel(doc.source_file, doc.page_or_slide)}</p>}
        </div>
        <CloseButton onClick={onClose} label="Close source text" />
      </div>
      <div className="sheet-body">
        {error && <LoadError message={error} onRetry={retry} />}
        {doc && !doc.highlight && <p className="text-warning">The quote could not be located on the cited page.</p>}
        {doc && doc.pages.map((page) => {
          const cited = page.page === doc.page_or_slide;
          return (
            <section key={page.page} className={cited ? 'source-page cited' : 'source-page'} ref={cited ? citedPage : undefined}>
              <div className="source-page-label">
                {pageLabel(doc.source_file, page.page).replace(/^./, (c) => c.toUpperCase())}
                {cited && <Badge tone="info">Cited</Badge>}
              </div>
              <div className="source-text">
                <PageBody page={page} highlight={cited ? doc.highlight : null} markRef={mark} />
              </div>
            </section>
          );
        })}
      </div>
    </aside>
  );
}
