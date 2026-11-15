"""FR3 CI authority: slide outcome statements are compared with the CI and never replace it."""
from src.clo_authority import compare_with_ci, corroborating_slides, find_span

CI_CLO1 = 'Explain how to clean missing data values in raw datasets'
CI_CLO2 = 'Evaluate imputation methods for incomplete datasets'
CI_TEXT = f'Course Learning Outcomes CLO1 {CI_CLO1}. CLO2 {CI_CLO2}. Course synopsis: this course covers data wrangling.'


def chunk(doc_id, page, level, *, tables='', restates=False, course='SAIA2143'):
    return {'course_code': course, 'doc_id': doc_id, 'pdf_page_no': page, 'evidence_level': level,
            'tables_markdown': tables, 'restates_clo': restates}


def fixture(slide_text, course='SAIA2143'):
    chunks = [chunk('ci.pdf', 1, 'CLO', tables=f'| No. | CLO | Statement |\n| 1 | CLO1 | {CI_CLO1} |\n| 2 | CLO2 | {CI_CLO2} |', course=course),
              chunk('deck.pdf', 2, 'Taught', restates=True, course=course)]
    lookup = {f'{course}::ci.pdf::1': CI_TEXT, f'{course}::deck.pdf::2': slide_text}
    return chunks, lookup


def statuses(result):
    return [(s['status'], s.get('ci_clo')) for page in result['slide_pages'] for s in page['statements']]


def test_find_span_ignores_spacing_case_and_punctuation_but_returns_page_text():
    page = 'Intro.  explain HOW to clean—missing data values, in raw datasets! End'
    assert find_span(CI_CLO1, page) == 'explain HOW to clean—missing data values, in raw datasets'
    assert find_span('Explain how to tidy missing data values', page) is None
    assert find_span('too short', page) is None


def test_slide_repeating_a_ci_clo_is_corroboration():
    chunks, lookup = fixture(f'Course Learning Outcomes CLO1: {CI_CLO1}.')
    result = compare_with_ci('SAIA2143', True, chunks, lookup)
    assert [s['clo'] for s in result['ci_statements']] == ['CLO1', 'CLO2']
    assert all(s['quoted_from_page'] for s in result['ci_statements'])
    assert statuses(result) == [('repeats_ci', 'CLO1')]


def test_slide_with_different_wording_for_the_same_clo_shows_both_statements():
    chunks, lookup = fixture('Course Learning Outcomes CLO2: Build web dashboards with React components.')
    statement = compare_with_ci('SAIA2143', True, chunks, lookup)['slide_pages'][0]['statements'][0]
    assert statement['status'] == 'differs_from_ci' and statement['ci_clo'] == 'CLO2'
    assert statement['statement'] == 'CLO2: Build web dashboards with React components.'
    assert statement['ci_statement'] == CI_CLO2 and (statement['ci_doc_id'], statement['ci_pdf_page_no']) == ('ci.pdf', 1)


def test_topic_goals_not_in_the_ci_are_flagged_and_footer_is_trimmed():
    slide = ('COURSE LEARNING OUTCOMES At the end of this topic, students should be able to: '
             'i. Define outliers in a dataset. ii. ' + CI_CLO1 + ' 2 UTM Faculty of Artificial Intelligence')
    chunks, lookup = fixture(slide)
    result = compare_with_ci('SAIA2143', True, chunks, lookup)
    statements = result['slide_pages'][0]['statements']
    assert statuses(result) == [('repeats_ci', 'CLO1'), ('not_in_ci', None)]
    assert statements[1]['statement'] == 'Define outliers in a dataset.'


def test_schedule_labels_are_not_read_as_differing_outcomes():
    chunks, lookup = fixture('Course Learning Outcomes Week 3 CLO2 Data merging lab session and quiz review')
    assert statuses(compare_with_ci('SAIA2143', True, chunks, lookup)) == []


def test_course_without_ci_marks_slide_outcomes_as_unable_to_establish_clo():
    chunks, lookup = fixture('Course Learning Outcomes CLO1: Explain machine learning concepts and terms.', course='SAIA2113')
    result = compare_with_ci('SAIA2113', False, chunks, lookup)
    assert result['ci_available'] is False and result['ci_statements'] == []
    assert statuses(result) == [('no_ci', None)]


def test_corroboration_needs_the_cited_ci_wording_on_the_slide():
    chunks, lookup = fixture(f'Course Learning Outcomes CLO1: {CI_CLO1}.')
    assert corroborating_slides(CI_CLO1, 'SAIA2143', chunks, lookup) == [
        {'doc_id': 'deck.pdf', 'pdf_page_no': 2, 'slide_quote': CI_CLO1}]
    assert corroborating_slides(CI_CLO2, 'SAIA2143', chunks, lookup) == []
    assert corroborating_slides(CI_CLO1, 'SAIA1013', chunks, lookup) == []
