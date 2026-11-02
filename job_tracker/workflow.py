import json
from contextlib import contextmanager
from datetime import date
from .db import now,set_status


@contextmanager
def pipeline_lock(path):
    try:
        fd=path.open('x',encoding='utf-8')
    except FileExistsError as exc:
        raise ValueError('Pipeline lock exists. Check for an active process before removing data/pipeline.lock after a crash') from exc
    try:
        import os
        with fd: fd.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def approve(db,job_id):
    app=db.execute('SELECT * FROM applications WHERE job_id=?',(job_id,)).fetchone()
    if not app or not app['generated_at']: raise ValueError('Generate and review documents before approval')
    from pathlib import Path
    if not all(Path(app[k]).is_file() for k in ('cv_path','letter_path')): raise ValueError('Draft documents are missing')
    db.execute('UPDATE applications SET approved_at=? WHERE job_id=?',(now(),job_id))
    db.execute('INSERT INTO events(job_id,status,occurred_at,note) VALUES(?,?,?,?)',(job_id,'Awaiting Approval',now(),'Human confirmed document approval; no submission performed'))


def followups(db):
    return [dict(r) for r in db.execute("SELECT j.id,j.title,j.employer,a.follow_up_at FROM applications a JOIN jobs j ON a.job_id=j.id WHERE a.submitted_at IS NOT NULL AND a.follow_up_at<=? AND j.status NOT IN ('Rejected by Employer','Offer Received','Withdrawn','Expired')",(date.today().isoformat(),))]


def import_email_events(db,path,authorized=False):
    if not authorized: raise ValueError('Email status import requires --authorized; no inbox access or email sending occurs')
    rows=json.loads(path.read_text(encoding='utf-8'))
    allowed={'Recruiter Response','Interview Scheduled','Interview Completed','Rejected by Employer','Offer Received'}
    if not isinstance(rows,list): raise ValueError('Email event import must be a JSON list')
    for row in rows:
        if row.get('status') not in allowed or not row.get('evidence','').strip(): raise ValueError('Each event requires an allowed status and reviewed evidence')
        marker='Email import: '+row['evidence']
        if db.execute('SELECT 1 FROM events WHERE job_id=? AND status=? AND note=?',(row['job_id'],row['status'],marker)).fetchone(): continue
        set_status(db,row['job_id'],row['status'],marker)
        if row.get('interview_at'):
            from datetime import datetime
            datetime.fromisoformat(row['interview_at'])
            db.execute('UPDATE applications SET interview_at=?,interview_notes=? WHERE job_id=?',(row['interview_at'],marker,row['job_id']))
    return len(rows)
