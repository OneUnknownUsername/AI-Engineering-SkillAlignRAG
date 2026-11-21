from pathlib import Path

from src.week4_audit_checks import unlisted_sources


def test_unlisted_sources_finds_course_files_added_after_the_audited_run(tmp_path):
    courses = tmp_path / "data" / "courses"
    listed = courses / "C1" / "02_Lecture_Slides_Taught" / "week1.pdf"
    added = courses / "C1" / "01_CI_CLO" / "ci.pdf"
    ignored = courses / "C1" / "01_CI_CLO" / "notes.txt"
    for path in (listed, added, ignored):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    manifest = {"sources": [{"path": listed.as_posix()}]}

    assert unlisted_sources(manifest, courses) == [added.as_posix()]
    assert unlisted_sources({"sources": manifest["sources"] + [{"path": added.as_posix()}]}, courses) == []
