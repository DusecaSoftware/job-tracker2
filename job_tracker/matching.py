import json
import re
from datetime import datetime,timezone,timedelta
from .db import set_status
WEIGHTS=dict(skills=30,tools=15,specialization=20,responsibilities=10,seniority=10,location=10,portfolio=5)
TOOLS=('figma','adobe illustrator','adobe photoshop','adobe indesign','sketch','adobe xd','canva','after effects')
ROLES=('graphic designer','ui/ux designer','ui designer','ux designer','web designer','product designer','brand identity designer','visual designer','digital designer','creative designer','illustration designer','packaging designer')


def eligibility(j):
    text=(j['location']+' '+j['description']).lower()
    if j['arrangement'].lower() in ('onsite','hybrid'):
        return ('Eligible','Local role') if any(x in j['location'].lower() for x in ('islamabad','rawalpindi')) else ('Ineligible','Outside target cities')
    if j['arrangement'].lower()!='remote': return 'Needs review','Work arrangement unspecified'
    if re.search(r'(?:must|only|restricted|eligible|reside|based).{0,35}(?:united states|usa|united kingdom|european union|canada|australia)|(?:us|usa|uk|eu|canada|australia)[ -]only',text) or any(x in text for x in ('us only','usa only','united states only','uk only','eu only','must reside in the us','pakistan excluded','not open to pakistan')): return 'Ineligible','Explicit country restriction'
    if any(x in text for x in ('worldwide','anywhere in the world','all countries','applicants in pakistan','pakistan eligible')) or j['location'].strip().lower()=='pakistan': return 'Eligible','Explicit worldwide/Pakistan eligibility; verify before applying'
    return 'Needs review','Remote does not establish Pakistan eligibility'


def score_job(j,p,weights=None):
    weights=WEIGHTS if weights is None else weights
    if set(weights)!=set(WEIGHTS) or any(not isinstance(v,(int,float)) or v<0 for v in weights.values()) or sum(weights.values())<=0: raise ValueError('Invalid scoring weights')
    text=(j['title']+' '+j['description']).lower(); facts=' '.join(p['skills']).lower()
    matched=[s for s in p['skills'] if s.lower() in text]
    required=[s for s in TOOLS if s in text]; missing=[s for s in required if s not in facts]
    eligible,reason=eligibility(j); role=any(r in j['title'].lower() for r in ROLES)
    components=dict(skills=min(1,len(matched)/3),tools=sum(s in facts for s in required)/len(required) if required else .5,specialization=float(role),responsibilities=min(1,len(matched)/2),seniority=.5,location=float(eligible=='Eligible'),portfolio=.5)
    if any(x in text for x in ('principal','director','10+ years','15+ years')):
        components['seniority']=0; missing.append('Verify seniority/experience requirements')
    if 'portfolio' in text: missing.append('Portfolio content requires manual review')
    if not role: eligible,reason='Ineligible','Outside design targets'
    return dict(score=round(sum(weights[k]*v for k,v in components.items())/sum(weights.values())*100,1),matching=matched,missing=missing,eligibility=eligible,explanation=reason+'; components='+json.dumps(components,sort_keys=True)+'; conservative rule score; seniority and portfolio require review; no ATS/interview guarantee')


def match_all(db,cfg,profile,weights=None):
    rows=db.execute("SELECT * FROM jobs WHERE status IN ('Discovered','Shortlisted','Rejected by matching criteria')").fetchall()
    for row in rows:
        j=dict(row); result=score_job(j,profile,weights); stale=False
        from .assessment import review_signals
        result['missing'].extend(review_signals(db,j))
        for key in ('published_at','deadline'):
            if j[key]:
                try:
                    dt=datetime.fromisoformat(j[key].replace('Z','+00:00'))
                    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    # A date-only deadline is open through that calendar day (UTC).
                    if key=='deadline' and re.fullmatch(r'\d{4}-\d{2}-\d{2}',j[key]):
                        dt+=timedelta(days=1)
                    stale |= dt<datetime.now(timezone.utc)-(timedelta(days=cfg.stale_days) if key=='published_at' else timedelta())
                except ValueError: result['missing'].append(f'Invalid {key}; verify date')
        db.execute('UPDATE jobs SET score=?,matching=?,missing=?,eligibility=?,explanation=? WHERE id=?',(result['score'],json.dumps(result['matching']),json.dumps(result['missing']),result['eligibility'],result['explanation'],j['id']))
        status='Expired' if stale else 'Shortlisted' if result['score']>=cfg.threshold and result['eligibility']=='Eligible' else 'Rejected by matching criteria' if result['eligibility']=='Ineligible' or result['eligibility']=='Eligible' and result['score']<cfg.threshold else 'Discovered'
        set_status(db,j['id'],status)
    return len(rows)
