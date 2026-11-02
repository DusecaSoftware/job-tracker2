import json
from pathlib import Path
from types import SimpleNamespace
from docx import Document
import pytest
from openpyxl import load_workbook
from job_tracker.db import connect,add_job,set_status
from job_tracker.config import Config
from job_tracker.sources import collect,parse_rss
from job_tracker.cv import digest,load_verified
from job_tracker.matching import score_job,match_all
from job_tracker.documents import generate
from job_tracker.report import build_report,metrics
from job_tracker.workflow import approve,followups,import_email_events,pipeline_lock


@pytest.fixture
def setup(tmp_path):
    cfg=Config(tmp_path,tmp_path/'input/master.docx'); cfg.prepare()
    db=connect(tmp_path/'data/test.sqlite3')
    doc=Document()
    facts=['Afsheen Khan','Figma','Graphic Design','Wireframing','SYNTHETIC TEST EXPERIENCE — not a real employer']
    for s in facts: doc.add_paragraph(s)
    doc.save(cfg.master_cv)
    p=dict(name='Afsheen Khan',skills=facts[1:4],experience=[facts[4]],education=[],projects=[],reviewed=True,master_sha256=digest(cfg.master_cv))
    (tmp_path/'input/profile.reviewed.json').write_text(json.dumps(p))
    job=dict(source='synthetic',source_id='1',url='https://example.invalid/job',title='Graphic Designer',employer='SYNTHETIC TEST COMPANY',description='Graphic Design Figma Wireframing. Remote worldwide.',location='Worldwide',arrangement='Remote')
    yield db,cfg,p,job
    db.close()


def test_full_review_lifecycle(setup):
    db,cfg,p,job=setup
    collect(db,[job],'synthetic'); assert match_all(db,cfg,load_verified(cfg))==1
    assert db.execute('SELECT status FROM jobs').fetchone()[0]=='Shortlisted'
    assert generate(db,cfg,p)==1
    assert generate(db,cfg,p)==0
    assert metrics(db)['Applications submitted']==0
    approve(db,1)
    set_status(db,1,'Submitted','Synthetic receipt',confirmed=True)
    set_status(db,1,'Recruiter Response','Synthetic reply')
    set_status(db,1,'Interview Scheduled','Synthetic invitation')
    db.execute("UPDATE applications SET follow_up_at='2020-01-01' WHERE job_id=1")
    assert len(followups(db))==1
    path=build_report(db,cfg); build_report(db,cfg)
    wb=load_workbook(path)
    assert wb.sheetnames==['Dashboard','Job Listings','Applications','Interview Tracker','Daily Metrics','Configuration']
    assert wb['Applications']['J2'].value
    assert len(wb['Dashboard']._charts)==1
    assert metrics(db)['Applications submitted']==1
    assert db.execute('SELECT count(*) FROM daily_metrics').fetchone()[0]==1


def test_unverified_fact_blocks_documents(setup):
    db,cfg,p,j=setup
    p['skills'].append('Invented tool')
    (cfg.home/'input/profile.reviewed.json').write_text(json.dumps(p))
    with pytest.raises(ValueError,match='Unverified'): load_verified(cfg)


def test_changed_master_blocks_profile(setup):
    db,cfg,p,j=setup
    d=Document(cfg.master_cv); d.add_paragraph('Changed'); d.save(cfg.master_cv)
    with pytest.raises(ValueError,match='SHA256'): load_verified(cfg)


@pytest.mark.parametrize('location,description,arrangement,expected',[
 ('US','US only worldwide','Remote','Ineligible'),
 ('Remote','Figma','Remote','Needs review'),
 ('Rawalpindi','','Hybrid','Eligible'),
 ('London','','Onsite','Ineligible'),
 ('Worldwide','Figma','Remote','Eligible')])
def test_eligibility(setup,location,description,arrangement,expected):
    db,cfg,p,j=setup
    j.update(location=location,description=description,arrangement=arrangement)
    assert score_job(j,p)['eligibility']==expected


def test_engineering_excluded(setup):
    db,cfg,p,j=setup
    j['title']='Senior DevOps Engineer'
    assert score_job(j,p)['eligibility']=='Ineligible'


def test_missing_tool_recorded(setup):
    db,cfg,p,j=setup
    j['description']+=' After Effects'
    assert 'after effects' in score_job(j,p)['missing']


def test_expired_deadline(setup):
    db,cfg,p,j=setup
    j['deadline']='2020-01-01'; collect(db,[j],'synthetic'); match_all(db,cfg,p)
    assert db.execute('SELECT status FROM jobs').fetchone()[0]=='Expired'


def test_failed_batch_rolls_back(setup):
    db,cfg,p,j=setup
    with pytest.raises(ValueError): collect(db,[j,{**j,'source_id':'2','url':'file:///bad'}],'synthetic')
    assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==0
    assert db.execute('SELECT count(*) FROM checkpoints').fetchone()[0]==0


def test_formula_injection_escaped(setup):
    db,cfg,p,j=setup
    j['employer']='=WEBSERVICE("https://example.invalid")'; collect(db,[j],'synthetic')
    path=build_report(db,cfg); wb=load_workbook(path)
    assert wb['Job Listings']['C2'].data_type=='s'
    assert wb['Job Listings']['C2'].value.startswith("'=")


def test_rss_parser():
    jobs=parse_rss(b'<rss><channel><item><title>Test: UI Designer</title><link>https://example.invalid/1</link><guid>x</guid><description>Worldwide</description></item></channel></rss>')
    assert jobs[0]['title']=='UI Designer'
    assert jobs[0]['employer']=='Test'


def test_email_import_requires_authorization_and_submission(setup):
    db,cfg,p,j=setup
    path=cfg.home/'input/events.json'; path.write_text('[{"job_id":1,"status":"Offer Received","evidence":"test"}]')
    with pytest.raises(ValueError,match='authorized'): import_email_events(db,path)
    collect(db,[j],'synthetic')
    with pytest.raises(ValueError,match='submission'): import_email_events(db,path,True)


def test_lock_prevents_overlap(tmp_path):
    path=tmp_path/'lock'
    with pipeline_lock(path):
        with pytest.raises(ValueError,match='lock'):
            with pipeline_lock(path): pass
    assert not path.exists()


def test_invalid_weights(setup):
    db,cfg,p,j=setup
    with pytest.raises(ValueError): score_job(j,p,{'skills':-1})


def test_duplicate_and_sensitive_signals(setup):
    from job_tracker.assessment import review_signals
    db,cfg,p,j=setup
    collect(db,[j],'synthetic')
    other={**j,'url':'http://example.invalid/other','source_id':'2','description':'application fee required'}
    flags=review_signals(db,other)
    assert len(flags)==3
    assert 'Potential duplicate' in flags[-1]


def test_master_cv_missing_fails_explicitly(tmp_path,monkeypatch,capsys):
    from job_tracker.cli import main
    monkeypatch.setenv('JOB_TRACKER_HOME',str(tmp_path))
    assert main(['match'])==1
    assert 'Master CV missing' in capsys.readouterr().err


def test_submitted_job_cannot_regress(setup):
    db,cfg,p,j=setup
    collect(db,[j],'synthetic'); match_all(db,cfg,p); generate(db,cfg,p); approve(db,1)
    set_status(db,1,'Submitted','Synthetic receipt',True)
    with pytest.raises(ValueError,match='regress'): set_status(db,1,'Discovered')


def test_matching_low_score_records_rejection(setup):
    db,cfg,p,j=setup
    strict=Config(cfg.home,cfg.master_cv,100)
    collect(db,[j],'synthetic'); match_all(db,strict,p)
    assert db.execute('SELECT status FROM jobs').fetchone()[0]=='Rejected by matching criteria'


def test_invalid_rss_clear_error():
    with pytest.raises(ValueError,match='invalid RSS'): parse_rss(b'<not closed')


# Verification audit: synthetic records stay isolated from the user's database.
def test_repeated_exports_preserve_application_and_event_history(setup):
    db,cfg,p,j=setup
    collect(db,[j],'synthetic'); match_all(db,cfg,p); generate(db,cfg,p); approve(db,1)
    set_status(db,1,'Submitted','SYNTHETIC receipt',True)
    set_status(db,1,'Recruiter Response','SYNTHETIC response')
    set_status(db,1,'Interview Scheduled','SYNTHETIC invitation')
    set_status(db,1,'Rejected by Employer','SYNTHETIC outcome')
    second={**j,'source_id':'2','url':'https://example.invalid/second'}
    collect(db,[second],'synthetic'); match_all(db,cfg,p); generate(db,cfg,p)
    db.execute('INSERT INTO daily_metrics VALUES(?,?)',('2020-01-01',json.dumps({'Applications submitted':1})))
    snapshot=lambda table:[tuple(r) for r in db.execute('SELECT * FROM '+table+' ORDER BY 1')]
    before={t:snapshot(t) for t in ('jobs','applications','events')}
    for _ in range(3):
        path=build_report(db,cfg)
        wb=load_workbook(path)
        assert [r[0] for r in wb['Job Listings'].iter_rows(min_row=2,values_only=True)]==[1,2]
        assert [r[0] for r in wb['Applications'].iter_rows(min_row=2,values_only=True)]==[1,2]
        assert wb['Applications']['J2'].value and wb['Applications']['J3'].value is None
        assert wb['Interview Tracker']['A2'].value==1
        wb.close()
    assert {t:snapshot(t) for t in before}==before
    assert db.execute('SELECT metrics FROM daily_metrics WHERE day=?',('2020-01-01',)).fetchone()[0]==json.dumps({'Applications submitted':1})
    assert db.execute('SELECT count(*) FROM daily_metrics').fetchone()[0]==2


def test_cli_pipeline_twice_is_idempotent_and_offline(setup,monkeypatch):
    import socket
    from job_tracker.cli import main
    db,cfg,p,j=setup
    monkeypatch.setenv('JOB_TRACKER_HOME',str(cfg.home))
    monkeypatch.setenv('MASTER_CV_PATH',str(cfg.master_cv))
    def forbid_network(*args,**kwargs): raise AssertionError('Unexpected network request')
    monkeypatch.setattr(socket,'create_connection',forbid_network)
    path=cfg.home/'input/audit.synthetic.json'; path.write_text(json.dumps([j]))
    for _ in range(2): assert main(['run','--file',str(path)])==0
    stored=connect(cfg.home/'data/tracker.sqlite3')
    assert stored.execute('SELECT count(*) FROM jobs').fetchone()[0]==1
    assert stored.execute('SELECT count(*) FROM applications').fetchone()[0]==1
    assert stored.execute('SELECT count(*) FROM applications WHERE submitted_at IS NOT NULL').fetchone()[0]==0
    assert stored.execute("SELECT count(*) FROM events WHERE status='Submitted'").fetchone()[0]==0
    app=stored.execute('SELECT * FROM applications').fetchone()
    for key in ('cv_path','letter_path'):
        path=Path(app[key]); assert path.is_relative_to(cfg.home/'output/documents')
        assert Document(path).paragraphs
    stored.close()


@pytest.mark.parametrize('approved,confirmed,evidence',[(False,True,'Synthetic'),(True,False,'Synthetic'),(True,True,'')])
def test_cli_submission_authorization_gate(setup,monkeypatch,approved,confirmed,evidence):
    from job_tracker.cli import main
    db,cfg,p,j=setup
    collect(db,[j],'synthetic'); match_all(db,cfg,p); generate(db,cfg,p)
    if approved: approve(db,1)
    db.commit()
    # CLI uses tracker.sqlite3; use SQLite backup to copy the isolated fixture.
    target=connect(cfg.home/'data/tracker.sqlite3'); db.backup(target); target.close()
    monkeypatch.setenv('JOB_TRACKER_HOME',str(cfg.home))
    args=['status','--job-id','1','--to','Submitted','--evidence',evidence]
    if confirmed: args.append('--confirmed')
    assert main(args)==1
    target=connect(cfg.home/'data/tracker.sqlite3')
    assert target.execute('SELECT submitted_at FROM applications').fetchone()[0] is None
    target.close()


def test_submission_cannot_rewrite_historical_receipt(setup):
    db,cfg,p,j=setup
    collect(db,[j],'synthetic'); match_all(db,cfg,p); generate(db,cfg,p); approve(db,1)
    set_status(db,1,'Submitted','SYNTHETIC original receipt',True)
    before=tuple(db.execute('SELECT submitted_at,submission_evidence FROM applications').fetchone())
    set_status(db,1,'Recruiter Response','SYNTHETIC reply')
    with pytest.raises(ValueError,match='already confirmed'):
        set_status(db,1,'Submitted','SYNTHETIC new receipt',True)
    assert tuple(db.execute('SELECT submitted_at,submission_evidence FROM applications').fetchone())==before


def test_empty_weights_are_invalid(setup):
    db,cfg,p,j=setup
    with pytest.raises(ValueError,match='weights'): score_job(j,p,{})


def test_date_only_deadline_remains_open_through_deadline_day(setup,monkeypatch):
    from datetime import datetime,timezone
    import job_tracker.matching as matching
    class AuditClock(datetime):
        @classmethod
        def now(cls,tz=None): return cls(2026,11,3,12,tzinfo=timezone.utc)
    monkeypatch.setattr(matching,'datetime',AuditClock)
    db,cfg,p,j=setup
    j['deadline']='2026-11-03'; collect(db,[j],'synthetic'); match_all(db,cfg,p)
    assert db.execute('SELECT status FROM jobs').fetchone()[0]=='Shortlisted'


def test_corrupt_docx_reports_cli_error(setup,monkeypatch,capsys):
    from job_tracker.cli import main
    db,cfg,p,j=setup
    cfg.master_cv.write_bytes(b'not a DOCX file')
    monkeypatch.setenv('JOB_TRACKER_HOME',str(cfg.home))
    monkeypatch.setenv('MASTER_CV_PATH',str(cfg.master_cv))
    assert main(['extract-cv'])==1
    assert 'Error:' in capsys.readouterr().err


def test_synthetic_pdf_ingestion_and_verified_profile(setup):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    from job_tracker.cv import extract
    db,cfg,p,j=setup
    path=cfg.home/'input/audit.synthetic.pdf'
    writer=PdfWriter(); page=writer.add_blank_page(width=612,height=792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 50 700 Td (Afsheen Khan) Tj 0 -20 Td (SYNTHETIC TEST CV - not actual candidate experience) Tj 0 -20 Td (Figma) Tj 0 -20 Td (Graphic Design) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    writer.write(path)
    assert 'SYNTHETIC TEST CV' in extract(path)
    pdfcfg=Config(cfg.home,path)
    p.update(master_sha256=digest(path),skills=['Figma','Graphic Design'],experience=['SYNTHETIC TEST CV - not actual candidate experience'])
    (cfg.home/'input/profile.reviewed.json').write_text(json.dumps(p))
    assert load_verified(pdfcfg)['skills']==['Figma','Graphic Design']


def test_corrupt_pdf_reports_cli_error(setup,monkeypatch,capsys):
    from job_tracker.cli import main
    db,cfg,p,j=setup
    path=cfg.home/'input/corrupt.synthetic.pdf'; path.write_bytes(b'broken PDF')
    monkeypatch.setenv('JOB_TRACKER_HOME',str(cfg.home))
    monkeypatch.setenv('MASTER_CV_PATH',str(path))
    assert main(['extract-cv'])==1
    assert 'Master CV is unreadable' in capsys.readouterr().err


def test_image_only_pdf_requires_text_version(tmp_path):
    from pypdf import PdfWriter
    from job_tracker.cv import extract
    path=tmp_path/'blank.synthetic.pdf'; w=PdfWriter(); w.add_blank_page(width=612,height=792); w.write(path)
    with pytest.raises(ValueError,match='No extractable CV text'): extract(path)
