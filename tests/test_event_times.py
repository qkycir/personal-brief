import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).parents[1] / 'skills/personal-brief/scripts/validate_event_times.py'
spec = importlib.util.spec_from_file_location('event_times', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EventTimeTests(unittest.TestCase):
    def record(self, source):
        return f'## EVT-20261114-01｜Example\n- source_time: {source}\n- observed_at: 2026-11-14T11:00:00+08:00\n'

    def test_duplicate_timezone_regression(self):
        result = module.validate(self.record('2026-11-08T15:17:16+08:00+08:00'))
        self.assertFalse(result['valid'])
        self.assertEqual(result['errors'][0]['field'], 'source_time')

    def test_preserves_known_precision(self):
        for value in ['2026-11-04', 'unknown', '2026-11-04T18:02+08:00', '2026-11-04T10:02:00Z']:
            with self.subTest(value=value):
                self.assertTrue(module.validate(self.record(value))['valid'])

    def test_impossible_or_ambiguous_instants_rejected(self):
        for value in ['2026-11-31', '2026-11-14T25:00+08:00', '2026-11-14T08:00:00']:
            with self.subTest(value=value):
                self.assertFalse(module.validate(self.record(value))['valid'])

    def test_missing_observation_and_duplicate_events(self):
        self.assertFalse(module.validate('## EVT-20261114-01｜Example\n- source_time: unknown\n')['valid'])
        record = self.record('2026-11-14')
        self.assertIn('duplicate_event_id', [x['error'] for x in module.validate(record + record)['errors']])

    def test_does_not_claim_semantic_date_validation(self):
        # Valid serialization may still be attached to the wrong quoted source.
        self.assertTrue(module.validate(self.record('2026-11-12T09:10+08:00'))['valid'])


if __name__ == '__main__':
    unittest.main()
