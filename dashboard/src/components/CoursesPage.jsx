import { Fragment } from 'react';
import { LEVELS } from '../api.js';
import useApi from '../useApi.js';
import LoadError from './LoadError.jsx';
import CiComparison from './CiComparison.jsx';
import { Badge, PageHeader } from './ui.jsx';
import { CourseDocuments } from './UploadDialog.jsx';

export default function CoursesPage({ title, workspace, onSignedOut }) {
  const { data: courses, error, retry } = useApi('/api/courses', onSignedOut);
  // The document list comes from the workspace; a saved run shown read-only has none.
  const documents = useApi(workspace ? '/api/documents' : null, onSignedOut).data;

  return (
    <section>
      <PageHeader title={title} />
      {error && <LoadError message={error} onRetry={retry} />}
      {!courses ? !error && <p className="loading">Loading…</p> : (
        <div className="card-grid">
          {courses.map((c) => (
            <article key={c.course_code} className="card">
              <div className="card-header">
                <h2 className="card-title">{c.course_code}</h2>
                <p className="card-description">{c.course_title}</p>
              </div>
              <div className="card-content">
                <dl className="kv">
                  {LEVELS.map((level) => (
                    <Fragment key={level}>
                      <dt>{level}</dt>
                      <dd>
                        {c.availability[level]
                          ? <Badge tone="supported">Available</Badge>
                          : <Badge tone="warning" title="Missing or could not be processed">Unavailable</Badge>}
                      </dd>
                    </Fragment>
                  ))}
                </dl>
                {documents && <CourseDocuments documents={documents.filter((d) => d.course_code === c.course_code)} />}
                {c.ci_comparison && <CiComparison comparison={c.ci_comparison} />}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
