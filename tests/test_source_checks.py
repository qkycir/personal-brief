import importlib.util
from pathlib import Path
import tempfile
import unittest

base=Path(__file__).parents[1]/'skills/personal-brief/scripts'
def module(name):
    spec=importlib.util.spec_from_file_location(name,base/(name+'.py'))
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
checks=module('source_checks'); store=module('brief_store')

class SourceChecks(unittest.TestCase):
    def test_pending_transcript_missing_hash_then_processed_and_changed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'transcript.txt'; p.write_text('Synthetic transcript')
            first=checks.transcript_probe(p, {'selected_path':str(p)})
            self.assertEqual(first['result'],'needs_read')
            self.assertNotIn('content_sha256',first)
            previous={'content_sha256':first['observed_sha256'],'processing_state':'processed'}
            self.assertEqual(checks.transcript_probe(p,previous)['result'],'unchanged')
            self.assertEqual(checks.transcript_probe(p,previous,True)['result'],'pending')
            self.assertEqual(checks.transcript_probe(p,dict(previous,processing_state='pending'))['result'],'needs_read')
            p.write_text('Changed text')
            self.assertEqual(checks.transcript_probe(p,previous)['result'],'needs_read')
            p.write_text('  ')
            self.assertEqual(checks.transcript_probe(p,previous)['result'],'pending')
            p.unlink(); self.assertEqual(checks.transcript_probe(p,previous)['result'],'pending')

    def test_ambiguous_chat_always_needs_body(self):
        current=dict(authorized=True,identity_status='confirmed',identity_key='id-1',preview_complete=True,
                     preview_kind='text',time_precise=True,observation_after_displayed_minute=True,
                     displayed_time='10:00',preview='Hello')
        previous=dict(current,body_verified=True)
        self.assertEqual(checks.chat_decision(current,previous)['result'],'unchanged')
        for changes in ({'preview_complete':False},{'preview_kind':'image'},{'time_precise':False},
                        {'identity_status':'display_name_only'},{'observation_after_displayed_minute':False},
                        {'identity_key':'id-2'},{'preview':'New'}):
            self.assertEqual(checks.chat_decision(dict(current,**changes),previous)['result'],'needs_read')
        self.assertEqual(checks.chat_decision(dict(current,authorized=False),previous)['result'],'skip')
        self.assertEqual(checks.chat_decision(current,{})['result'],'needs_read')

    def test_source_progress_cannot_inherit_old_result(self):
        with tempfile.TemporaryDirectory() as d:
            c=store.connect(d)
            try:
                old=dict(id='s',source='chat',run_id='r1',observed_at='2026-01-01T10:00:00+00:00',coverage='checked',boundary='old',incremental_result='unchanged')
                store.apply(c,{'sources':[old]})
                new=dict(store.get(c,'sources','s'),run_id='r2',observed_at='2026-01-01T11:00:00+00:00',coverage='read new message')
                store.apply(c,{'sources':[new]})
                saved=store.get(c,'sources','s')
                self.assertNotIn('incremental_result',saved)
                self.assertEqual(saved['last_incremental_run_id'],'r2')
                self.assertEqual(saved['last_incremental_check'],new['observed_at'])
                self.assertEqual(saved['boundary'],'old')
                self.assertEqual(store.apply(c,{'sources':[saved]}),0)
                transcript=dict(new,id='t',selected_path='synthetic.txt')
                store.apply(c,{'sources':[transcript]})
                self.assertIsNone(store.get(c,'sources','t')['content_sha256'])
                self.assertTrue(store.check(c)['valid'])
            finally:c.close()

if __name__=='__main__':unittest.main()
