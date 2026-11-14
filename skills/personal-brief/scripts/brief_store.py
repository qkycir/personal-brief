#!/usr/bin/env python3
"""Local personal-brief ledger. No source access or external side effects."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

KINDS = ('events', 'sources', 'processed_mail', 'tasks', 'verifications', 'documents', 'runs', 'receipts')
TIME_KEYS = ('source_time', 'observed_at', 'message_time', 'quoted_source_time', 'deadline', 'activity_date', 'alarm', 'verified_at')
DOC_PATH = re.compile(r'(?:events|source-state|mail-processed|tasks|profile|focus|status)\.md|runs/[A-Za-z0-9_-]+/(?:collection|handoff|organize|verification)\.md')

def now():
    return datetime.now(timezone.utc).isoformat()

def encoded(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True)

def connect(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    c = sqlite3.connect(root / 'brief.sqlite3', timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    INSERT OR IGNORE INTO meta VALUES('schema_version','1');
    CREATE TABLE IF NOT EXISTS records(
      kind TEXT NOT NULL, id TEXT NOT NULL, run_id TEXT,
      source_key TEXT, source_time TEXT, state TEXT,
      payload TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY(kind,id));
    CREATE UNIQUE INDEX IF NOT EXISTS event_source ON records(source_key)
      WHERE kind='events' AND source_key IS NOT NULL;
    CREATE INDEX IF NOT EXISTS record_run ON records(kind,run_id);
    CREATE TABLE IF NOT EXISTS revisions(
      seq INTEGER PRIMARY KEY, kind TEXT, id TEXT, prior_payload TEXT,
      payload TEXT NOT NULL, changed_at TEXT NOT NULL);
    ''')
    if c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != '1':
        raise ValueError('unsupported schema version')
    return c

def time_ok(value, precise=False):
    if value == 'unknown' and not precise:
        return True
    if not isinstance(value, str): return False
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            date.fromisoformat(value)
            return not precise
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value):
            return False
        return datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except ValueError: return False

def validate(kind, row):
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
        raise ValueError(f'{kind}: nonempty id required')
    for key in TIME_KEYS:
        if key in row and not time_ok(row[key], key in ('observed_at','verified_at')):
            raise ValueError(f'{kind}/{row["id"]}: invalid {key}')
    required = {
      'events': ('run_id','source_key','title','source','locator','source_time','observed_at','excerpt','summary','body_complete','applicability'),
      'sources': ('source','observed_at','coverage','boundary'),
      'processed_mail': ('run_id','cache_path','uidvalidity','uid','event_ids'),
      'tasks': ('run_id','title','state','event_ids'),
      'verifications': ('run_id','event_ids','result','verified_at','evidence'),
      'documents': ('body',),
      'runs': ('phase',),
      'receipts': ('task_id','kind','at'),
    }[kind]
    if any(k not in row for k in required):
        raise ValueError(f'{kind}/{row["id"]}: missing fields {set(required)-row.keys()}')
    if kind == 'events':
        if not isinstance(row['body_complete'], bool): raise ValueError('body_complete must be boolean')
        if not isinstance(row['source_key'], str) or not row['source_key']: raise ValueError('source_key required')
        if row.get('is_quote') is True and row.get('relative_date_expression'):
            if row.get('deadline','unknown') != 'unknown' or row.get('activity_date','unknown') != 'unknown':
                if row.get('quoted_source_time','unknown') == 'unknown' or row.get('body_quote_boundary_verified') is not True:
                    raise ValueError('relative quoted date requires verified original date and quote boundary')
    if kind == 'documents' and (not DOC_PATH.fullmatch(row['id']) or row['id'] in ('events.md','source-state.md','tasks.md','mail-processed.md')):
        raise ValueError('document path outside exported report allowlist')
    if kind == 'verifications' and row['result'] not in ('pass','pending','reject'):
        raise ValueError('invalid verification result')
    if kind in ('tasks','processed_mail','verifications'):
        if not isinstance(row['event_ids'],list) or any(not isinstance(x,str) or not x for x in row['event_ids']):
            raise ValueError('event_ids must be a list of nonempty strings')
    if kind == 'documents' and not isinstance(row['body'],str):
        raise ValueError('document body must be text')
    if kind == 'tasks' and row['state'] not in ('candidate','active','completed','cancelled','pending','withdrawn_invalid_source'):
        raise ValueError('invalid task state')

def rows(c, kind, run_id=None):
    sql = 'SELECT payload FROM records WHERE kind=?'
    args = [kind]
    if run_id: sql += ' AND run_id=?'; args.append(run_id)
    return [json.loads(r[0]) for r in c.execute(sql+' ORDER BY id', args)]

def get(c, kind, key):
    r = c.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind,key)).fetchone()
    return json.loads(r[0]) if r else None

def reference_errors(c):
    errors=[]
    for kind in ('tasks','verifications','processed_mail'):
        for row in rows(c,kind):
            prefix=f'{kind}/{row["id"]}: '
            ids=row.get('event_ids',[])
            if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):
                errors.append(prefix+'invalid event references'); continue
            if any(get(c,'events',eid) is None for eid in ids):
                errors.append(prefix+'missing event reference')
            if kind=='tasks' and row.get('state')=='active':
                v=get(c,'verifications',row.get('verification_id',''))
                if not v or v.get('result')!='pass' or not set(ids).issubset(v.get('event_ids',[])):
                    errors.append(prefix+'active task needs passed verification covering its evidence')
                if not row.get('reminder_id') or not row.get('last_synced_content'):
                    errors.append(prefix+'active task needs read-back reminder ID and snapshot')
    return errors

def apply(c, batch):
    if not isinstance(batch,dict) or set(batch)-set(KINDS): raise ValueError('unknown batch kind')
    count = 0
    with c:
        for kind in KINDS:
            for row in batch.get(kind,[]):
                row = dict(row)
                validate(kind,row)
                prior = get(c,kind,row['id'])
                if kind == 'sources':
                    if row.get('selected_path'):
                        row.setdefault('content_sha256', None)
                    if row.get('run_id'):
                        # A copied old result is not evidence of a new check.
                        if prior and prior.get('run_id') != row['run_id'] and row.get('incremental_result') == prior.get('incremental_result'):
                            row.pop('incremental_result', None)
                        row['last_incremental_run_id'] = row['run_id']
                        row['last_incremental_check'] = row['observed_at']
                if kind == 'tasks' and prior and prior['state'] == 'completed' and row['state'] != 'completed':
                    raise ValueError('completed task cannot be automatically reopened')
                if prior == row: continue
                c.execute('INSERT INTO revisions(kind,id,prior_payload,payload,changed_at) VALUES(?,?,?,?,?)',
                          (kind,row['id'],encoded(prior) if prior else None,encoded(row),now()))
                c.execute('''INSERT INTO records VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(kind,id)
                DO UPDATE SET run_id=excluded.run_id,source_key=excluded.source_key,source_time=excluded.source_time,
                state=excluded.state,payload=excluded.payload,updated_at=excluded.updated_at''',
                (kind,row['id'],row.get('run_id'),row.get('source_key') if kind=='events' else None,
                 row.get('source_time'),row.get('state',row.get('phase')),encoded(row),now()))
                count += 1
        # Validate references after the whole transaction, allowing events and mail progress together.
        errors=reference_errors(c)
        if errors: raise ValueError('; '.join(errors))
    return count

def atomic_text(path, body):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.brief-')
    try:
        with os.fdopen(fd,'w') as f: f.write(body)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def export(c,root):
    root=Path(root)
    names={'events':'events.md','sources':'source-state.md','processed_mail':'mail-processed.md','tasks':'tasks.md'}
    for kind,name in names.items():
        out=['# '+{'events':'事件记录','sources':'来源进度','processed_mail':'邮件处理记录','tasks':'待办记录'}[kind],
             '\n> 从 brief.sqlite3 导出；请通过记录工具更新，勿独立修改。\n']
        for row in rows(c,kind):
            out += ['## '+row.get('title',row['id']), '\n```json\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n```\n']
        atomic_text(root/name,'\n'.join(out)+'\n')
    for row in rows(c,'documents'):
        if row['id'] in names.values(): raise ValueError('reserved structured export name')
        atomic_text(root/row['id'],row['body']+'\n')
    for run in rows(c,'runs'):
        vs=[r for r in rows(c,'verifications',run['id'])]
        if vs:
            atomic_text(root/'runs'/run['id']/'verification.md','# 原文核验记录\n\n'+ '\n\n'.join('```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```' for v in vs)+'\n')

def check(c):
    errors=[]
    for kind in KINDS:
        for row in rows(c,kind):
            try: validate(kind,row)
            except ValueError as e: errors.append(str(e))
    errors.extend(reference_errors(c))
    if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': errors.append('sqlite integrity check failed')
    return {'valid':not errors,'counts':{k:len(rows(c,k)) for k in KINDS},'errors':errors}

def ready(c,run_id,phase):
    r=get(c,'runs',run_id)
    if not r: raise ValueError('run not registered')
    if r.get('phase') not in ('collecting','collected','partial'):
        raise ValueError('only collecting or handed-off runs can be readied; ended runs cannot reopen')
    report=check(c)
    if not report['valid']: raise ValueError('record validation failed')
    if not get(c,'documents',f'runs/{run_id}/collection.md'): raise ValueError('collection report missing')
    if not r.get('coverage'): raise ValueError('run coverage required, including gaps')
    r.update(phase=phase,ready_for_organize=True,event_ids=[e['id'] for e in rows(c,'events',run_id)])
    apply(c,{'runs':[r], 'documents':[{'id':f'runs/{run_id}/handoff.md','run_id':run_id,
        'body':'# 采集交接\n\nready_for_organize: true\n\n```json\n'+json.dumps(r,ensure_ascii=False,indent=2)+'\n```'}]})
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',required=True,type=Path)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init'); sub.add_parser('check'); sub.add_parser('export')
    a=sub.add_parser('apply'); a.add_argument('file',type=Path)
    a=sub.add_parser('query'); a.add_argument('kind',choices=KINDS); a.add_argument('--id'); a.add_argument('--run-id')
    a=sub.add_parser('ready'); a.add_argument('--run-id',required=True); a.add_argument('--phase',choices=('collected','partial'),required=True)
    args=p.parse_args()
    c=connect(args.data_dir)
    try:
        if args.command=='apply': result={'changed':apply(c,json.loads(args.file.read_text()))}; export(c,args.data_dir)
        elif args.command=='query': result=get(c,args.kind,args.id) if args.id else rows(c,args.kind,args.run_id)
        elif args.command=='ready': result=ready(c,args.run_id,args.phase); export(c,args.data_dir)
        elif args.command=='export': export(c,args.data_dir); result={'exported':True}
        else: result=check(c)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 1 if isinstance(result,dict) and result.get('valid') is False else 0
    except (ValueError,sqlite3.IntegrityError) as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False)); return 1
    finally: c.close()

if __name__=='__main__': raise SystemExit(main())
