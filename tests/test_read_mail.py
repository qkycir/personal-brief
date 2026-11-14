import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('reader', Path(__file__).parents[1] / 'skills/personal-brief/scripts/read_mail.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)

class Mailbox:
    capabilities = ('ID',)
    instances = []
    fail_body = False
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.instances.append(self)
    def login(self, *args): pass
    def _simple_command(self, command, value):
        assert command == 'ID'
        self.calls.append(('ID',))
        return 'OK', []
    def select(self, folder, readonly=False):
        assert readonly
        self.calls.append(('select', folder, readonly))
        return 'OK', [b'1']
    def response(self, name): return name, [b'42']
    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == 'SEARCH': return 'OK', [b'7']
        if args[1] == '(RFC822.SIZE)': return 'OK', [b'1 (RFC822.SIZE 200)']
        assert args[1] == '(BODY.PEEK[] FLAGS INTERNALDATE)'
        if self.fail_body: return 'NO', []
        return 'OK', [(b'1 (BODY[] {80}', b'Subject: hello\r\nMessage-ID: <sample>\r\n\r\nprivate body')]
    def logout(self): pass

class ReadOnlyMailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'mail-accounts.json').write_text(json.dumps({'accounts': [dict(name='test', address='test@example.org', host='example.org', folders=['INBOX'], keychain_service='test')]}))
        Mailbox.instances.clear()
        Mailbox.fail_body = False
    def run_reader(self, *extra):
        out = io.StringIO()
        with patch.object(reader.imaplib, 'IMAP4_SSL', Mailbox), patch.object(reader, 'secret', return_value='secret'), patch('sys.argv', ['reader', '--data-dir', str(self.root), '--run-id', 'test', *extra]), contextlib.redirect_stdout(out):
            result = reader.run()
        self.assertNotIn('private body', out.getvalue())
        self.assertNotIn('secret', out.getvalue())
        return result
    def test_check_never_fetches_or_advances(self):
        self.assertEqual(self.run_reader('--check'), 0)
        self.assertFalse((self.root / 'mail-state.json').exists())
        self.assertEqual(Mailbox.instances[-1].calls, [('ID',), ('select', 'INBOX', True)])
    def test_fetch_is_peek_and_retries_preserve_cache(self):
        self.assertEqual(self.run_reader(), 0)
        caches = list((self.root/'mail-cache/test').glob('test-*.json'))
        self.assertEqual(len(caches), 1)
        self.assertEqual(json.loads(caches[0].read_text())['records'][0]['body'], 'private body')
        self.assertEqual(reader.brief_store.get(reader.brief_store.connect(self.root),'sources','mail:test|INBOX')['cursor']['last_uid'], 7)
        self.assertEqual(self.run_reader(), 0)
        self.assertEqual(len(list((self.root/'mail-cache/test').glob('test-*.json'))), 2)
        self.assertEqual(json.loads(caches[0].read_text())['records'][0]['uid'], 7)
        self.assertFalse(any(c[0] == 'FETCH' for c in Mailbox.instances[-1].calls))
    def test_failure_keeps_cursor(self):
        Mailbox.fail_body = True
        self.assertEqual(self.run_reader(), 2)
        self.assertFalse((self.root/'mail-state.json').exists())
    def test_uidvalidity_change_restarts_window(self):
        reader.brief_store.apply(reader.brief_store.connect(self.root), {'sources':[{'id':'mail:test|INBOX','source':'mail','observed_at':'2026-01-01T00:00:00+00:00','coverage':{},'boundary':'500','cursor':{'uidvalidity':'41','last_uid':500}}]})
        self.assertEqual(self.run_reader(), 0)
        search = next(c for c in Mailbox.instances[-1].calls if c[0] == 'SEARCH')
        self.assertEqual(search[2], 'SINCE')
    def test_attachment_is_not_message_body(self):
        raw = b'MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\nContent-Type: text/plain\r\n\r\nbody\r\n--x\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="note.txt"\r\n\r\nattachment\r\n--x--\r\n'
        item = reader.extract(raw)
        self.assertEqual(item['body'], 'body')
        self.assertEqual(item['attachments'][0]['name'], 'note.txt')

if __name__ == '__main__': unittest.main()
