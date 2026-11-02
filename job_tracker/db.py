"""Transactional storage; status history is append only through this API."""
import json
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

STATUSES = ('Discovered', 'Shortlisted', 'Rejected by matching criteria', 'CV Ready',
            'Awaiting Approval', 'Submitted', 'Recruiter Response', 'Interview Scheduled',
            'Interview Completed', 'Rejected by Employer', 'Offer Received', 'Withdrawn',
            'Expired', 'No Response')


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url):
    p = urlsplit(url.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Job URL must be HTTP(S), with no embedded credentials')
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', urlencode(sorted(query)), ''))


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
    INSERT OR IGNORE INTO schema_version VALUES(1);
    CREATE TABLE IF NOT EXISTS jobs(
      id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
      url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, employer TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
      arrangement TEXT NOT NULL DEFAULT 'Unknown', salary TEXT NOT NULL DEFAULT '',
      employment_type TEXT NOT NULL DEFAULT '', published_at TEXT, deadline TEXT,
      discovered_at TEXT NOT NULL, last_seen TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Discovered', score REAL, matching TEXT,
      missing TEXT, eligibility TEXT, explanation TEXT, UNIQUE(source,source_id));
    CREATE TABLE IF NOT EXISTS applications(
      job_id INTEGER PRIMARY KEY REFERENCES jobs(id), cv_path TEXT, letter_path TEXT,
      generated_at TEXT, approved_at TEXT, submitted_at TEXT, submission_evidence TEXT,
      follow_up_at TEXT, interview_at TEXT, interview_notes TEXT);
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
      status TEXT NOT NULL, occurred_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS checkpoints(
      source TEXT PRIMARY KEY, completed_at TEXT NOT NULL, details TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS daily_metrics(
      day TEXT PRIMARY KEY, metrics TEXT NOT NULL);
    ''')
    return db


def add_job(db, job):
    url = normalize_url(job['url'])
    required = ('source', 'source_id', 'title', 'employer')
    if any(not str(job.get(k, '')).strip() for k in required):
        raise ValueError('Job requires source, source_id, title and employer')
    existing = db.execute('SELECT id FROM jobs WHERE url=? OR (source=? AND source_id=?)',
                          (url, job['source'], str(job['source_id']))).fetchone()
    if existing:
        db.execute('UPDATE jobs SET last_seen=? WHERE id=?', (now(), existing['id']))
        return existing['id'], False
    fields = required + ('description', 'location', 'arrangement', 'salary', 'employment_type', 'published_at', 'deadline')
    values = [job.get(k, None if k in ('published_at', 'deadline') else '') for k in fields]
    stamp = now()
    cur = db.execute(f"INSERT INTO jobs({','.join(fields)},url,discovered_at,last_seen) VALUES({','.join('?' for _ in range(len(fields)+3))})", values + [url, stamp, stamp])
    db.execute('INSERT INTO events(job_id,status,occurred_at) VALUES(?,?,?)', (cur.lastrowid, 'Discovered', stamp))
    return cur.lastrowid, True


def set_status(db, job_id, status, note='', confirmed=False):
    if status not in STATUSES:
        raise ValueError('Unknown application status')
    job = db.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not job:
        raise ValueError('Unknown job')
    app = db.execute('SELECT * FROM applications WHERE job_id=?', (job_id,)).fetchone()
    if status == 'Submitted' and (not confirmed or not note.strip() or not app or not app['approved_at']):
        raise ValueError('Submission requires approval, explicit confirmation and evidence')
    if status in ('Recruiter Response', 'Interview Scheduled', 'Interview Completed', 'Rejected by Employer', 'Offer Received', 'No Response') and (not app or not app['submitted_at']):
        raise ValueError('Outcome requires a confirmed submission')
    if job['status'] == status:
        return
    if status == 'Submitted' and app and app['submitted_at']:
        raise ValueError('Submission already confirmed; original date and evidence must be preserved')
    if app and app['submitted_at'] and status in ('Discovered','Shortlisted','Rejected by matching criteria','CV Ready','Awaiting Approval'):
        raise ValueError('Confirmed submissions cannot regress into preparation statuses')
    stamp = now()
    db.execute('UPDATE jobs SET status=? WHERE id=?', (status, job_id))
    db.execute('INSERT INTO events(job_id,status,occurred_at,note) VALUES(?,?,?,?)', (job_id, status, stamp, note))
    if status == 'Submitted':
        db.execute('UPDATE applications SET submitted_at=?,submission_evidence=? WHERE job_id=?', (stamp, note, job_id))


def checkpoint(db, source, details):
    db.execute('INSERT INTO checkpoints VALUES(?,?,?) ON CONFLICT(source) DO UPDATE SET completed_at=excluded.completed_at,details=excluded.details', (source, now(), json.dumps(details)))
