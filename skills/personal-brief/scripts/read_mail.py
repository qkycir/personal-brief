#!/usr/bin/env python3
"""Read-only IMAP ingestion. Credentials stay in macOS Keychain; output is local."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import brief_store
import argparse, email, fcntl, hashlib, html, imaplib, json, os, re, ssl, subprocess, tempfile, uuid
from datetime import datetime, timedelta
from email import policy
from zoneinfo import ZoneInfo

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.mail-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def secret(account):
    r=subprocess.run(['/usr/bin/security','find-generic-password','-s',account['keychain_service'],'-a',account['address'],'-w'], capture_output=True, text=True)
    if r.returncode: raise RuntimeError('credential_unavailable')
    return r.stdout.rstrip('\n')

def extract(raw):
    msg=email.message_from_bytes(raw,policy=policy.default)
    plain=[]; rich=[]; attachments=[]
    for part in msg.walk():
        if part.get_content_maintype()=='multipart': continue
        filename=part.get_filename()
        if filename or part.get_content_disposition()=='attachment':
            attachments.append({'name':filename,'type':part.get_content_type()}); continue
        if part.get_content_type() not in ('text/plain','text/html'): continue
        try: text=part.get_content()
        except Exception: text=part.get_payload(decode=True).decode('utf-8','replace')
        if not isinstance(text,str): continue
        if part.get_content_type()=='text/plain': plain.append(text)
        else: rich.append(html.unescape(re.sub('<[^>]+>',' ',text)))
    body='\n'.join(plain or rich)
    return {'message_id':str(msg.get('Message-ID','')),'subject':str(msg.get('Subject','')),
        'from':str(msg.get('From','')),'to':str(msg.get('To','')),'date':str(msg.get('Date','')),
        'in_reply_to':str(msg.get('In-Reply-To','')),'references':str(msg.get('References','')),
        'body':body[:100000],'body_truncated':len(body)>100000,'attachments':attachments,
        'attachments_read':False,'content_sha256':hashlib.sha256(raw).hexdigest()}

def run():
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',required=True,type=Path)
    p.add_argument('--run-id',required=True)
    p.add_argument('--account', help='Only read this configured account name')
    p.add_argument('--timezone',default='UTC',help='IANA timezone from private configuration')
    p.add_argument('--lookback-days',type=int,default=30,help='Authorized initial window after a new UIDVALIDITY')
    p.add_argument('--check',action='store_true',help='Authenticate and open folders read-only; do not fetch messages')
    args=p.parse_args()
    if args.lookback_days < 1: p.error('lookback-days must be positive')
    try: zone=ZoneInfo(args.timezone)
    except Exception: p.error('unknown IANA timezone')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_id): p.error('invalid run-id')
    os.umask(0o077)
    root=args.data_dir.resolve()
    lock=open(root/'.mail-read.lock','a')
    try:
        try: fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('mail_reader_already_running')
        accounts=json.loads((root/'mail-accounts.json').read_text())['accounts']
        if args.account:
            accounts=[a for a in accounts if a['name']==args.account]
            if not accounts: p.error('unknown account')
        db=brief_store.connect(root)
        state={r['id'][5:]:r['cursor'] for r in brief_store.rows(db,'sources') if r['id'].startswith('mail:')}
        report={'run_id':args.run_id,'checked_at':datetime.now(zone).isoformat(),'check_only':args.check,'accounts':[]}
        for a in accounts:
            result={'account':a['name'],'folders':[],'status':'ok','stage':'connect'}
            client=None
            try:
                client=imaplib.IMAP4_SSL(a['host'],a.get('port',993),ssl_context=ssl.create_default_context(),timeout=20)
                result['stage']='keychain'
                password=secret(a)
                result['stage']='login'
                client.login(a['address'],password)
                del password
                if any(x in ('ID', b'ID') for x in client.capabilities):
                    imaplib.Commands.setdefault('ID',('AUTH','SELECTED'))
                    client._simple_command('ID','("name" "personal-brief" "version" "0.1" "vendor" "personal-brief")')
                result['stage']='readonly_folder'
                for folder in a['folders']:
                    typ,count=client.select(folder,readonly=True)
                    if typ!='OK': raise RuntimeError('folder_readonly_open_failed')
                    validity=client.response('UIDVALIDITY')[1]
                    validity=next((x.decode() for x in (validity or []) if x),None)
                    if not validity: raise RuntimeError('uidvalidity_missing')
                    key=a['name']+'|'+folder
                    prev=state.get(key,{})
                    reset=prev.get('uidvalidity')!=validity
                    fs={'folder':folder,'readonly':True,'message_count':int(count[0]),'uidvalidity':validity,'uid_reset':reset,'records':[]}
                    if args.check:
                        result['folders'].append(fs); continue
                    last=0 if reset else int(prev.get('last_uid',0))
                    since=(datetime.now(zone)-timedelta(days=args.lookback_days)).strftime('%d-%b-%Y')
                    typ,found=client.uid('SEARCH',None,'UID',str(last+1)+':*') if last else client.uid('SEARCH',None,'SINCE',since)
                    if typ!='OK': raise RuntimeError('uid_search_failed')
                    uids=sorted(int(x) for x in (found[0] or b'').split() if int(x)>last)
                    fs['pending_count']=len(uids)
                    fs['partial']=len(uids)>500
                    for uid in uids[:500]:
                        typ,meta=client.uid('FETCH',str(uid),'(RFC822.SIZE)')
                        joined=b' '.join(x for x in meta if isinstance(x,bytes))
                        size=re.search(rb'RFC822.SIZE\s+(\d+)',joined)
                        if typ!='OK' or not size: raise RuntimeError('message_size_unavailable')
                        if int(size.group(1))>10*1024*1024:
                            fs['records'].append({'uid':uid,'status':'blocked_large_message','size':int(size.group(1))})
                            fs['partial']=True
                            break
                        typ,parts=client.uid('FETCH',str(uid),'(BODY.PEEK[] FLAGS INTERNALDATE)')
                        if typ!='OK': raise RuntimeError('message_fetch_failed')
                        payload=next((x[1] for x in parts if isinstance(x,tuple) and isinstance(x[1],bytes)),None)
                        if payload is None: raise RuntimeError('message_body_missing')
                        item=extract(payload);item['uid']=uid;item['source_key']=key
                        fs['records'].append(item)
                        last=uid
                    result['folders'].append(fs)
                    # Persist content before advancing mailbox cursor; retry is deduplicable.
                    save(root/'mail-cache'/args.run_id/(a['name']+'-'+hashlib.sha256(folder.encode()).hexdigest()[:8]+'-'+uuid.uuid4().hex+'.json'),fs)
                    state[key]={'uidvalidity':validity,'last_uid':last,'last_checked':report['checked_at']}
                    brief_store.apply(db, {'sources':[{'id':'mail:'+key, 'source':'mail', 'observed_at':report['checked_at'], 'coverage':{'partial':fs['partial'], 'fetched':len(fs['records'])}, 'boundary':str(last), 'cursor':state[key]}]})
            except Exception as e:
                result['status']='blocked'
                # Do not log server exceptions, which could contain account or credential material.
                result['error_type']=type(e).__name__
                result['reason']=str(e) if type(e) is RuntimeError else 'authentication_or_network_error'
            finally:
                if client:
                    try: client.logout()
                    except Exception: pass
            report['accounts'].append(result)
        # No message content printed to the calling chat.
        summary={'run_id':args.run_id,'check_only':args.check,'accounts':[{'account':x['account'],'status':x['status'],'reason':x.get('reason'),'stage':x.get('stage'),'error_type':x.get('error_type'),'fetched':sum(len(y['records']) for y in x['folders']),'partial':any(y.get('partial') for y in x['folders'])} for x in report['accounts']]}
        save(root/'mail-cache'/args.run_id/'report.json',summary)
        print(json.dumps(summary,ensure_ascii=False))
        return 0 if all(x['status']=='ok' for x in report['accounts']) else 2
    finally:
        if 'db' in locals(): db.close()
        lock.close()

if __name__=='__main__': raise SystemExit(run())
