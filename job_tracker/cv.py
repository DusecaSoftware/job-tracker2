"""Only reviewed exact CV excerpts may appear in candidate documents."""
import hashlib
import json
import re
from zipfile import BadZipFile
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from lxml.etree import XMLSyntaxError


def extract(path):
    if not path.is_file(): raise ValueError(f'Master CV missing: {path}')
    try:
        if path.suffix.lower()=='.pdf':
            text='\n'.join(p.extract_text() or '' for p in PdfReader(path).pages)
        elif path.suffix.lower()=='.docx':
            d=Document(path)
            text='\n'.join([p.text for p in d.paragraphs]+[c.text for t in d.tables for r in t.rows for c in r.cells])
        else: raise ValueError('CV must be PDF or DOCX')
    except (BadZipFile, PackageNotFoundError, PyPdfError, XMLSyntaxError, KeyError) as exc:
        raise ValueError('Master CV is unreadable, corrupt or encrypted; provide a valid text-based PDF or DOCX') from exc
    if not text.strip(): raise ValueError('No extractable CV text; a text-based CV is required')
    return text


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text): return re.sub(r'\s+',' ',text).strip().casefold()


def load_verified(cfg):
    text=extract(cfg.master_cv); path=cfg.home/'input/profile.reviewed.json'
    if not path.exists(): raise ValueError('Review input/profile.reviewed.json first; see README')
    p=json.loads(path.read_text(encoding='utf-8'))
    if p.get('reviewed') is not True or p.get('master_sha256')!=digest(cfg.master_cv): raise ValueError('Profile needs review and current master CV SHA256')
    if normalize(p.get('name',''))!='afsheen khan' or normalize(p['name']) not in normalize(text): raise ValueError('CV must identify Afsheen Khan')
    for section in ('skills','experience','education','projects','contact'):
        if not isinstance(p.get(section,[]),list): raise ValueError(f'{section} must contain exact CV excerpts')
        for fact in p.get(section,[]):
            if not isinstance(fact,str) or not fact.strip() or normalize(fact) not in normalize(text): raise ValueError(f'Unverified excerpt in {section}')
    if not p.get('skills') or not p.get('experience'): raise ValueError('Reviewed skills and experience are required')
    return p
