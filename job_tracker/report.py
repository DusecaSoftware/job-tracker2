"""Excel is a rebuildable view of SQLite, never the source of history."""
import json
import os
from datetime import date
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import PatternFill
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.table import Table, TableStyleInfo
from .db import STATUSES


def safe(v):
    return "'"+v if isinstance(v,str) and v[:1] in ('=','+','-','@') else v


def tab(ws, headers, rows, name):
    ws.append(headers)
    for row in rows:
        ws.append([safe(v) for v in row])
    if not rows:
        ws.append([None]*len(headers))
    t=Table(displayName=name,ref=ws.dimensions)
    t.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True)
    ws.add_table(t)
    ws.freeze_panes='A2'
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width=min(60,max(18,max(len(str(c.value or '')) for c in col[:50])+2))


def metrics(db):
    def count(sql,params=()):
        return db.execute(sql,params).fetchone()[0]
    def reached(status):
        return count('SELECT count(DISTINCT job_id) FROM events WHERE status=?',(status,))
    return {'Jobs found':count('SELECT count(*) FROM jobs'),
            'Relevant jobs':count("SELECT count(*) FROM jobs WHERE eligibility='Eligible'"),
            'Shortlisted':reached('Shortlisted'),
            'Tailored CVs':count('SELECT count(*) FROM applications WHERE generated_at IS NOT NULL'),
            'Applications prepared':count('SELECT count(*) FROM applications'),
            'Applications submitted':count('SELECT count(*) FROM applications WHERE submitted_at IS NOT NULL'),
            'Recruiter responses':reached('Recruiter Response'),
            'Interviews':reached('Interview Scheduled'),
            'Rejections':reached('Rejected by Employer'), 'Offers':reached('Offer Received'),
            'Pending applications':count("SELECT count(*) FROM applications a JOIN jobs j ON a.job_id=j.id WHERE submitted_at IS NOT NULL AND j.status NOT IN ('Rejected by Employer','Offer Received','Withdrawn','Expired')")}


def build_report(db,cfg):
    m=metrics(db)
    db.execute('INSERT INTO daily_metrics VALUES(?,?) ON CONFLICT(day) DO UPDATE SET metrics=excluded.metrics',(date.today().isoformat(),json.dumps(m)))
    wb=Workbook(); wb.remove(wb.active)
    for name in ('Dashboard','Job Listings','Applications','Interview Tracker','Daily Metrics','Configuration'):
        wb.create_sheet(name)
    dash=wb['Dashboard']; dash.append(['Metric','Value'])
    for item in m.items(): dash.append(item)
    idx={dash.cell(i,1).value:i for i in range(2,dash.max_row+1)}
    for label,num,den in [('Response rate','Recruiter responses','Applications submitted'),('Interview rate','Interviews','Applications submitted'),('Offer conversion rate','Offers','Interviews')]:
        dash.append([label,f'=IFERROR(B{idx[num]}/B{idx[den]},0)']); dash.cell(dash.max_row,2).number_format='0.0%'
    jobs=db.execute('SELECT id,title,employer,source,url,location,arrangement,salary,employment_type,published_at,deadline,discovered_at,status,score,matching,missing,eligibility,explanation FROM jobs ORDER BY id').fetchall()
    tab(wb['Job Listings'],['ID','Role','Employer','Source','URL','Location','Arrangement','Salary','Employment Type','Published','Deadline','Discovered','Status','Match Score','Matching Skills','Missing Requirements','Eligibility','Explanation'],jobs,'JobListings')
    for status,color in [('Shortlisted','C6EFCE'),('Expired','FFC7CE'),('Awaiting Approval','FFEB9C')]:
        wb['Job Listings'].conditional_formatting.add(f'A2:R{max(2,len(jobs)+1)}',FormulaRule(formula=[f'$M2="{status}"'],fill=PatternFill('solid',fgColor=color)))
    apps=db.execute('SELECT j.id,j.title,j.employer,j.url,j.status,a.cv_path,a.letter_path,a.generated_at,a.approved_at,a.submitted_at,a.follow_up_at,a.submission_evidence FROM applications a JOIN jobs j ON a.job_id=j.id').fetchall()
    tab(wb['Applications'],['ID','Role','Employer','URL','Status','CV Version','Cover Letter','Generated','Approved','Submitted','Follow Up','Evidence'],apps,'Applications')
    wb['Applications'].conditional_formatting.add(f'A2:L{max(2,len(apps)+1)}',FormulaRule(formula=['AND($K2<>"",$K2<=TEXT(TODAY(),"yyyy-mm-dd"),$J2<>"")'],fill=PatternFill('solid',fgColor='FFEB9C')))
    interviews=db.execute("SELECT j.id,j.title,j.employer,j.status,a.interview_at,a.interview_notes FROM applications a JOIN jobs j ON a.job_id=j.id WHERE EXISTS(SELECT 1 FROM events e WHERE e.job_id=j.id AND e.status LIKE 'Interview%')").fetchall()
    tab(wb['Interview Tracker'],['ID','Role','Employer','Status','Interview At','Notes'],interviews,'Interviews')
    history=db.execute('SELECT day,metrics FROM daily_metrics ORDER BY day').fetchall()
    tab(wb['Daily Metrics'],['Day',*m],[[r[0],*[json.loads(r[1]).get(k,0) for k in m]] for r in history],'DailyMetrics')
    tab(wb['Configuration'],['Setting','Value'],[['Candidate','Afsheen Khan'],['Design targets','Graphic, UI/UX, web, brand and visual design'],['Threshold',cfg.threshold],['Stale days',cfg.stale_days],['Master CV',str(cfg.master_cv)],['Submission','Manual confirmation only'],['AI','No paid API required']],'Configuration')
    dash.append([]); dash.append(['Status','Unique jobs reaching status']); start=dash.max_row+1
    for s in STATUSES:
        dash.append([s,db.execute('SELECT count(DISTINCT job_id) FROM events WHERE status=?',(s,)).fetchone()[0]])
    chart=BarChart(); chart.title='Application status history'
    chart.add_data(Reference(dash,min_col=2,min_row=start-1,max_row=dash.max_row),titles_from_data=True)
    chart.set_categories(Reference(dash,min_col=1,min_row=start,max_row=dash.max_row)); dash.add_chart(chart,'D2')
    queries=[('Source performance','SELECT source,count(*),count(a.submitted_at) FROM jobs j LEFT JOIN applications a ON j.id=a.job_id GROUP BY source'),('Work arrangement','SELECT arrangement,count(*) FROM jobs GROUP BY arrangement'),('Match score distribution',"SELECT CASE WHEN score IS NULL THEN 'Unmatched' WHEN score<50 THEN '0–49' WHEN score<75 THEN '50–74' ELSE '75–100' END,count(*) FROM jobs GROUP BY 1")]
    for label,sql in queries:
        dash.append([]); dash.append([label,'Jobs','Submitted' if label=='Source performance' else ''])
        for row in db.execute(sql): dash.append([safe(v) for v in row])
    for label,period in [('Weekly','-7 days'),('Monthly','-1 month')]:
        dash.append([label+' submissions (rolling)',db.execute("SELECT count(DISTINCT job_id) FROM events WHERE status='Submitted' AND occurred_at>=datetime('now',?)",(period,)).fetchone()[0]])
    dash.column_dimensions['A'].width=40; dash.column_dimensions['B'].width=22; dash.freeze_panes='A2'
    path=cfg.home/'output/Afsheen_Job_Tracker.xlsx'; tmp=path.with_suffix('.tmp.xlsx')
    wb.save(tmp); os.replace(tmp,path)
    return path
