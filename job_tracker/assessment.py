"""Non-authoritative review signals. A warning never proves fraud or duplication."""
from datetime import datetime,timezone
import re


def review_signals(db,job):
    flags=[]
    text=(job.get('title','')+' '+job.get('description','')).lower()
    if any(x in text for x in ('application fee','pay to apply','bank account password','purchase equipment from')):
        flags.append('Sensitive/payment request: independently verify employer; not a fraud determination')
    if job.get('url','').startswith('http://'):
        flags.append('Unencrypted job URL: verify the official employer listing')
    normalize=lambda s:re.sub(r'\W+','',s).casefold()
    for other in db.execute('SELECT id,title,employer,url FROM jobs'):
        if other['url']!=job['url'] and normalize(other['title'])==normalize(job['title']) and normalize(other['employer'])==normalize(job['employer']):
            flags.append(f'Potential duplicate of job {other["id"]}; manual review required')
            break
    return flags
