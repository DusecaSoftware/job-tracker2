"""Exercise the labelled import example without a candidate CV or reviewed profile."""
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook

from job_tracker.config import Config
from job_tracker.db import connect
from job_tracker.matching import match_all
from job_tracker.report import build_report
from job_tracker.sources import collect, load_jobs


def test_three_synthetic_examples_match_and_export_without_real_profile(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / 'fixtures/jobs.synthetic.example.json'
    jobs = load_jobs(fixture)
    assert len(jobs) == 3
    assert all('SYNTHETIC' in j['description'] and '.invalid/' in j['url'] for j in jobs)
    cfg = Config(tmp_path, tmp_path / 'input/NO_CANDIDATE_CV_PROVIDED.pdf')
    cfg.prepare()
    db = connect(tmp_path / 'data/tracker.sqlite3')
    # Matching-only unit facts; no substitute CV, approval, or profile file is created.
    test_facts = {'skills': ['Figma', 'Graphic Design', 'Wireframing']}
    try:
        assert collect(db, jobs, 'synthetic-example') == 3
        with db:
            assert match_all(db, cfg, test_facts) == 3
        states = [tuple(r) for r in db.execute('SELECT status,eligibility FROM jobs ORDER BY id')]
        assert states == [('Shortlisted', 'Eligible'), ('Shortlisted', 'Eligible'),
                          ('Rejected by matching criteria', 'Ineligible')]
        history = [tuple(r) for r in db.execute('SELECT * FROM events ORDER BY id')]
        assert collect(db, jobs, 'synthetic-example') == 0
        with db:
            match_all(db, cfg, test_facts)
            first = build_report(db, cfg)
            second = build_report(db, cfg)
        assert first == second
        assert [tuple(r) for r in db.execute('SELECT * FROM events ORDER BY id')] == history
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 3
        assert db.execute('SELECT count(*) FROM applications').fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM events WHERE status='Submitted'").fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM daily_metrics').fetchone()[0] == 1
        with ZipFile(second) as archive:
            assert archive.testzip() is None
        wb = load_workbook(second)
        try:
            assert wb.sheetnames == ['Dashboard', 'Job Listings', 'Applications',
                                     'Interview Tracker', 'Daily Metrics', 'Configuration']
            assert [r[0] for r in wb['Job Listings'].iter_rows(min_row=2, values_only=True)] == [1, 2, 3]
            assert wb['Applications']['A2'].value is None
        finally:
            wb.close()
        assert not cfg.master_cv.exists()
        assert not (tmp_path / 'input/profile.reviewed.json').exists()
    finally:
        db.close()
