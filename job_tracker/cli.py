import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.error import URLError
from dotenv import load_dotenv
from .config import Config
from .db import connect,set_status
from .logging_setup import configure
from .workflow import pipeline_lock,approve,followups,import_email_events

COMMANDS=['init','validate','collect','match','generate','sync-excel','run','follow-ups','extract-cv','approve','status','import-email-status']


def main(argv=None):
    parser=argparse.ArgumentParser(description='Private background design job workflow for Afsheen Khan')
    parser.add_argument('command',choices=COMMANDS)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--file',type=Path,help='User-provided JSON job/event import')
    parser.add_argument('--wwr',action='store_true',help='Opt in to official WWR design RSS; verify current terms first')
    parser.add_argument('--weights',type=Path,help='JSON scoring weight overrides')
    parser.add_argument('--job-id',type=int)
    parser.add_argument('--to',choices=__import__('job_tracker.db',fromlist=['STATUSES']).STATUSES)
    parser.add_argument('--evidence',default='')
    parser.add_argument('--confirmed',action='store_true')
    parser.add_argument('--authorized',action='store_true')
    parser.add_argument('--follow-up',help='ISO follow-up date, YYYY-MM-DD')
    args=parser.parse_args(argv)
    load_dotenv(override=False)
    logger=None
    try:
        cfg=Config.load()
        if args.dry_run:
            print(f'Dry run: {args.command}; configuration valid; no network requests, database or document writes')
            return 0
        cfg.prepare(); logger=configure(cfg.home/'logs/events.jsonl')
        with pipeline_lock(cfg.home/'data/pipeline.lock'):
            db=connect(cfg.home/'data/tracker.sqlite3')
            try:
                with db:
                    if args.command in ('init','validate'):
                        print('Configuration valid; SQLite schema version 1 initialized')
                        print('Master CV: '+('present' if cfg.master_cv.is_file() else 'missing; matching and documents are blocked'))
                    if args.command=='extract-cv':
                        from .cv import extract,digest
                        text=extract(cfg.master_cv)
                        path=cfg.home/'input/master_cv.extracted.txt'; path.write_text(text,encoding='utf-8')
                        print(f'Private extraction: {path}; SHA256: {digest(cfg.master_cv)}')
                    if args.command in ('collect','run'):
                        from .sources import collect,load_jobs,fetch_wwr
                        if not args.file and not args.wwr: print('No collection source selected; use --file or opt in with --wwr')
                        if args.file: print(f'Imported {collect(db,load_jobs(args.file),"json-import")} new jobs')
                        if args.wwr: print(f'Collected {collect(db,fetch_wwr(),"WWR")} new jobs')
                    if args.command in ('match','generate','run'):
                        from .cv import load_verified
                        profile=load_verified(cfg)
                        if args.command in ('match','run'):
                            from .matching import match_all
                            weights=json.loads(args.weights.read_text()) if args.weights else None
                            print(f'Matched {match_all(db,cfg,profile,weights)} jobs')
                        if args.command in ('generate','run'):
                            from .documents import generate
                            print(f'Generated {generate(db,cfg,profile)} draft applications; none submitted')
                    if args.command=='approve':
                        approve(db,args.job_id); print('Documents approved; application not submitted')
                    if args.command=='status':
                        if not args.job_id or not args.to: raise ValueError('status requires --job-id and --to')
                        if args.to in ('CV Ready','Awaiting Approval','Shortlisted'): raise ValueError('Use match/generate for preparation statuses')
                        if not args.evidence.strip(): raise ValueError('Manual status updates require --evidence')
                        set_status(db,args.job_id,args.to,args.evidence,args.confirmed)
                        if args.follow_up:
                            from datetime import date
                            date.fromisoformat(args.follow_up)
                            db.execute('UPDATE applications SET follow_up_at=? WHERE job_id=?',(args.follow_up,args.job_id))
                        print('Recorded confirmed status; no submission or email sent')
                    if args.command=='import-email-status':
                        if not args.file: raise ValueError('Provide reviewed email events using --file')
                        print(f'Reviewed {import_email_events(db,args.file,args.authorized)} email status events')
                    if args.command in ('follow-ups','run'): print(json.dumps(followups(db)))
                    if args.command in ('sync-excel','run'):
                        from .report import build_report
                        print(build_report(db,cfg))
                logger.info('command_complete:'+args.command)
            finally: db.close()
        return 0
    except (ValueError,OSError,sqlite3.Error,URLError,KeyError,TypeError) as exc:
        # Do not log CV text, credentials or entire remote responses.
        if logger: logger.error('command_failed:'+args.command+':'+type(exc).__name__)
        print(f'Error: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
