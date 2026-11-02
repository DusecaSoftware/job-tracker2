"""Deterministic, free drafting with only verified CV excerpts."""
import hashlib
import json
import os
from pathlib import Path
from docx import Document
from docx.shared import Pt
from .db import now,set_status


def save_doc(doc,path):
    tmp=path.with_suffix('.tmp.docx')
    doc.save(tmp); os.replace(tmp,path)


def base_doc():
    doc=Document(); style=doc.styles['Normal']; style.font.name='Calibri'; style.font.size=Pt(11)
    return doc


def generate(db,cfg,profile):
    generated=0
    for job in db.execute("SELECT * FROM jobs WHERE status='Shortlisted'").fetchall():
        if db.execute('SELECT 1 FROM applications WHERE job_id=?',(job['id'],)).fetchone(): continue
        # Opaque stable directory avoids employer-controlled filenames and path traversal.
        version=hashlib.sha256((profile['master_sha256']+json.dumps(dict(job),sort_keys=True)).encode()).hexdigest()[:12]
        folder=cfg.home/'output/documents'/f"job-{job['id']}-{version}"
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        cv=base_doc(); cv.add_heading(profile['name'],0)
        for fact in profile.get('contact',[]): cv.add_paragraph(fact)
        cv.add_paragraph(f"Application draft for {job['title']} — {job['employer']}")
        cv.add_heading('Skills',1)
        skills=sorted(profile['skills'],key=lambda s:s.lower() not in job['description'].lower())
        for skill in skills: cv.add_paragraph(skill)
        for section in ('experience','education','projects'):
            if profile.get(section):
                cv.add_heading(section.title(),1)
                for fact in profile[section]: cv.add_paragraph(fact)
        letter=base_doc(); letter.add_heading('Cover Letter — Draft for Review',0)
        letter.add_paragraph(f"Dear Hiring Team at {job['employer']},")
        letter.add_paragraph(f"I am applying for the {job['title']} role. My relevant experience and skills are outlined below.")
        relevant=[s for s in skills if s.lower() in job['description'].lower()]
        if relevant: letter.add_paragraph('Relevant skills: '+', '.join(relevant))
        for fact in profile['experience']: letter.add_paragraph(fact)
        letter.add_paragraph('I would welcome the opportunity to discuss how my design experience could contribute to your team.')
        letter.add_paragraph('Sincerely,\n'+profile['name'])
        cv_path=folder/'CV.docx'; letter_path=folder/'Cover_Letter.docx'
        save_doc(cv,cv_path); save_doc(letter,letter_path)
        stamp=now()
        db.execute('INSERT INTO applications(job_id,cv_path,letter_path,generated_at) VALUES(?,?,?,?)',(job['id'],str(cv_path),str(letter_path),stamp))
        set_status(db,job['id'],'CV Ready',note='Verified CV excerpts; deterministic draft')
        set_status(db,job['id'],'Awaiting Approval',note='Human document review required')
        generated+=1
    return generated
