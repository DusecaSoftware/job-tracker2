"""Explicit opt-in RSS or user-provided JSON. No scraping or login automation."""
import json
import time
import xml.etree.ElementTree as ET
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from email.utils import parsedate_to_datetime
from .db import add_job,checkpoint
WWR_FEED='https://weworkremotely.com/categories/remote-design-jobs.rss'


def parse_rss(content):
    try:
        root=ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError('Source returned invalid RSS XML') from exc
    jobs=[]
    for item in root.findall('./channel/item'):
        title=item.findtext('title',''); employer,sep,role=title.partition(':')
        published=item.findtext('pubDate'); url=item.findtext('link','').strip()
        jobs.append(dict(source='We Work Remotely',source_id=item.findtext('guid') or url,url=url,title=role.strip() if sep else title,employer=employer.strip() if sep else 'Unspecified',description=item.findtext('description',''),location='Unspecified',arrangement='Remote',published_at=parsedate_to_datetime(published).isoformat() if published else None))
    return jobs


def fetch_wwr(attempts=3,delay=2):
    if not 1<=attempts<=5 or delay<1: raise ValueError('Invalid retry/rate limits')
    for attempt in range(attempts):
        time.sleep(delay)
        try:
            with urlopen(Request(WWR_FEED,headers={'User-Agent':'AfsheenJobTracker/0.1 personal RSS reader'}),timeout=30) as response:
                content=response.read(5_000_001)
                if len(content)>5_000_000: raise ValueError('Feed size exceeds limit')
                return parse_rss(content)
        except HTTPError as exc:
            if exc.code in (401,403,429): raise ValueError(f'Access stopped: HTTP {exc.code}; respect source restrictions') from exc
            if exc.code<500 or attempt==attempts-1: raise
        except (URLError,TimeoutError):
            if attempt==attempts-1: raise
        time.sleep(delay*2**attempt)


def collect(db,jobs,source):
    with db:
        added=sum(add_job(db,j)[1] for j in jobs)
        checkpoint(db,source,{'received':len(jobs),'added':added})
    return added


def load_jobs(path):
    jobs=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(jobs,list) or any(not isinstance(j,dict) for j in jobs): raise ValueError('JSON import must be a list of job objects')
    return jobs
