import sqlite3
import pytest
from job_tracker.config import Config
from job_tracker.db import connect, add_job, normalize_url, set_status
from job_tracker.cli import main


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / 'test.sqlite3')
    yield connection
    connection.close()


@pytest.fixture
def job():
    return dict(source='synthetic', source_id='test-1', url='https://example.invalid/design?utm_source=test', title='Graphic Designer', employer='Synthetic Test Company')


def test_deduplication(db, job):
    first, added = add_job(db, job)
    assert added
    job['source_id'] = 'other'
    assert add_job(db, job) == (first, False)
    assert db.execute('SELECT count(*) FROM events').fetchone()[0] == 1


def test_source_id_dedup(db, job):
    add_job(db, job)
    job['url'] = 'https://example.invalid/changed'
    assert add_job(db, job)[1] is False


def test_submission_requires_evidence_and_approval(db, job):
    id_, _ = add_job(db, job)
    with pytest.raises(ValueError):
        set_status(db, id_, 'Submitted', confirmed=True)
    db.execute('INSERT INTO applications(job_id,approved_at) VALUES(?,?)', (id_, '2026-01-01'))
    set_status(db, id_, 'Submitted', note='Manual submission receipt test', confirmed=True)
    assert db.execute('SELECT submitted_at FROM applications').fetchone()[0]


def test_unsubmitted_outcome_rejected(db, job):
    id_, _ = add_job(db, job)
    with pytest.raises(ValueError):
        set_status(db, id_, 'Offer Received')


def test_transaction_rollback(db, job):
    with pytest.raises(RuntimeError):
        with db:
            add_job(db, job)
            raise RuntimeError('simulated interruption')
    assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0


def test_schema_repeatable(tmp_path):
    path = tmp_path / 'db'
    connect(path).close()
    db = connect(path)
    assert db.execute('SELECT version FROM schema_version').fetchone()[0] == 1
    db.close()


def test_config_validation(monkeypatch):
    monkeypatch.setenv('SHORTLIST_THRESHOLD', '101')
    with pytest.raises(ValueError):
        Config.load()


def test_dry_run_no_files(tmp_path, monkeypatch):
    monkeypatch.setenv('JOB_TRACKER_HOME', str(tmp_path / 'private'))
    assert main(['init', '--dry-run']) == 0
    assert not (tmp_path / 'private').exists()


def test_normalization():
    assert normalize_url('https://EXAMPLE.invalid/job/?utm_source=a&id=2#x') == 'https://example.invalid/job?id=2'
    with pytest.raises(ValueError):
        normalize_url('file:///private')
