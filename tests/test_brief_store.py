import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('store',Path(__file__).parents[1]/'skills/personal-brief/scripts/brief_store.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

def event(**extra):
    x=dict(id='E1',run_id='r1',source_key='app|original|message1',title='通知',source='chat',locator='原消息',source_time='2026-11-04T18:02:00+08:00',observed_at='2026-11-14T11:00:00+08:00',excerpt='明天提交',summary='提交',body_complete=True,applicability='confirmed')
    x.update(extra);return x

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.c=s.connect(self.root);self.addCleanup(self.c.close)
    def test_bad_time_rolls_back_cursor_and_events(self):
        with self.assertRaises(ValueError):
            s.apply(self.c,{'events':[event(),event(id='E2',source_key='other',source_time='2026-11-04T18:02:00+08:00+08:00')],'sources':[dict(id='c',source='chat',observed_at='2026-11-14T11:00:00+08:00',coverage={},boundary='new')]})
        self.assertEqual(s.rows(self.c,'events'),[]);self.assertEqual(s.rows(self.c,'sources'),[])
    def test_repeat_is_idempotent_source_duplicate_rejected(self):
        self.assertEqual(s.apply(self.c,{'events':[event()]}),1)
        self.assertEqual(s.apply(self.c,{'events':[event()]}),0)
        with self.assertRaises(Exception):s.apply(self.c,{'events':[event(id='E2')]})
        self.assertEqual(len(s.rows(self.c,'events')),1)
    def test_quote_date_requires_original_evidence(self):
        with self.assertRaises(ValueError):s.apply(self.c,{'events':[event(is_quote=True,relative_date_expression='明天',deadline='2026-11-05')]})
        s.apply(self.c,{'events':[event(is_quote=True,relative_date_expression='明天',deadline='2026-11-05',quoted_source_time='2026-11-04T18:02:00+08:00',body_quote_boundary_verified=True)]})
    def test_completed_task_cannot_reopen_and_history_kept(self):
        s.apply(self.c,{'events':[event()],'tasks':[dict(id='t',run_id='r1',title='提交',state='completed',event_ids=['E1'])]})
        with self.assertRaises(ValueError):s.apply(self.c,{'tasks':[dict(id='t',run_id='r1',title='提交',state='pending',event_ids=['E1'])]})
        self.assertEqual(s.get(self.c,'tasks','t')['state'],'completed')
    def test_ready_requires_coverage_and_export_is_rebuildable(self):
        s.apply(self.c,{'events':[event()],'runs':[dict(id='r1',phase='collecting',coverage={'qq':'partial'})],'documents':[dict(id='runs/r1/collection.md',body='partial: older tail not covered')]})
        s.ready(self.c,'r1','partial');s.export(self.c,self.root)
        self.assertIn('partial',(self.root/'runs/r1/handoff.md').read_text())
        (self.root/'events.md').write_text('broken');s.export(self.c,self.root)
        self.assertIn('明天提交',(self.root/'events.md').read_text())
    def test_same_name_sources_are_not_collapsed(self):
        def row(i):return dict(id=i,source='wechat',display_name='同名群',identity_status='ambiguous',observed_at='2026-11-14T11:00:00+08:00',coverage='metadata',boundary='unknown')
        s.apply(self.c,{'sources':[row('observation1'),row('observation2')]})
        self.assertEqual(len(s.rows(self.c,'sources')),2)
    def test_active_task_needs_verification(self):
        with self.assertRaises(ValueError):s.apply(self.c,{'events':[event()],'tasks':[dict(id='t',run_id='r1',title='提交',state='active',event_ids=['E1'])]})
        self.assertEqual(s.rows(self.c,'events'),[])
    def test_missing_reference_does_not_mark_mail_processed(self):
        with self.assertRaises(ValueError):s.apply(self.c,{'processed_mail':[dict(id='m',run_id='r1',cache_path='mail.json',uidvalidity='1',uid=2,event_ids=['missing'])]})
        self.assertEqual(s.rows(self.c,'processed_mail'),[])
    def test_reschedule_keeps_id_and_prior_evidence(self):
        s.apply(self.c,{'events':[event(deadline='2026-11-05')]})
        s.apply(self.c,{'events':[event(deadline='2026-11-06',change_reason='source correction')]})
        self.assertEqual(len(s.rows(self.c,'events')),1)
        prior=json.loads(self.c.execute('SELECT prior_payload FROM revisions ORDER BY seq DESC LIMIT 1').fetchone()[0])
        self.assertEqual(prior['deadline'],'2026-11-05')

    def test_check_reports_broken_references(self):
        s.apply(self.c,{'events':[event()],'tasks':[dict(id='t',run_id='r1',title='check',state='pending',event_ids=['E1'])]})
        # Simulate an externally damaged database, not an allowed write route.
        self.c.execute("DELETE FROM records WHERE kind='events'");self.c.commit()
        result=s.check(self.c)
        self.assertFalse(result['valid'])
        self.assertTrue(any('missing event reference' in x for x in result['errors']))

    def test_ready_does_not_reopen_finished_run(self):
        for phase in ('organized','partial_organized','aborted'):
            s.apply(self.c,{'runs':[dict(id='r1',phase=phase,coverage={'qq':'checked'})]})
            with self.assertRaises(ValueError):s.ready(self.c,'r1','partial')
            self.assertEqual(s.get(self.c,'runs','r1')['phase'],phase)

    def test_bad_document_rolls_back_whole_batch(self):
        with self.assertRaises(ValueError):
            s.apply(self.c,{'events':[event()],'documents':[dict(id='focus.md',body={'not':'text'})]})
        self.assertEqual(s.rows(self.c,'events'),[])

if __name__=='__main__':unittest.main()
