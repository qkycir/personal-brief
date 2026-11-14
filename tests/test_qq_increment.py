import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).parents[1]/'skills/personal-brief/scripts/source_checks.py'
spec=importlib.util.spec_from_file_location('checks',path);checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)

class QQIncrementTests(unittest.TestCase):
    def pair(self, **changes):
        old=dict(source='QQ',authorized=True,identity_match='unique_local',identity_key='local-1',
                 displayed_time='昨天21:17',observed_at='2026-11-15T00:03:00+08:00',
                 preview='[图片]',preview_kind='image',preview_observed=True,unread_count=0,
                 acceptance='body_checked')
        cur=dict(old,displayed_time='星期六',observed_at='2026-11-16T08:00:00+08:00');cur.update(changes)
        return cur,dict(accepted_list_observation=old,pending_incremental=False)
    def decide(self,**changes):
        cur,old=self.pair(**changes);return checks.chat_decision(cur,old)
    def test_same_image_and_relative_date_transition_skips(self):
        self.assertEqual(self.decide()['result'],'unchanged')
    def test_same_truncated_preview_skips_after_checked(self):
        cur,old=self.pair();cur['preview']=old['accepted_list_observation']['preview']='Long text…'
        self.assertEqual(checks.chat_decision(cur,old)['result'],'unchanged')
    def test_preview_change_enters(self):self.assertEqual(self.decide(preview='different')['result'],'needs_read')
    def test_new_date_enters_even_same_image(self):self.assertEqual(self.decide(displayed_time='昨天')['reason'],'time_changed')
    def test_duplicate_identity_enters(self):self.assertEqual(self.decide(identity_match='ambiguous')['reason'],'identity_uncertain')
    def test_new_identity_enters(self):self.assertEqual(self.decide(identity_key='other')['reason'],'identity_changed')
    def test_unknown_time_enters(self):self.assertEqual(self.decide(displayed_time='未知')['reason'],'unresolved_time')
    def test_unread_increase_enters(self):self.assertEqual(self.decide(unread_count=1)['reason'],'unread_increased')
    def test_pending_not_masked_by_same_list(self):
        cur,old=self.pair();old['pending_incremental']=True
        self.assertEqual(checks.chat_decision(cur,old)['reason'],'unprocessed_increment')
    def test_missing_snapshot_not_silently_migrated(self):
        cur,_=self.pair();self.assertEqual(checks.chat_decision(cur,{})['reason'],'no_accepted_snapshot')
    def test_type_preview_current_day_still_needs_read(self):
        cur,old=self.pair();cur['displayed_time']='今天'
        old['accepted_list_observation'].update(displayed_time='今天',observed_at=cur['observed_at'])
        self.assertEqual(checks.chat_decision(cur,old)['reason'],'open_time_bucket')
    def test_same_minute_may_hide_new_message(self):
        cur,old=self.pair(displayed_time='10:00',observed_at='2026-11-15T10:00:40+08:00')
        old['accepted_list_observation'].update(displayed_time='10:00',observed_at='2026-11-15T10:00:01+08:00')
        self.assertEqual(checks.chat_decision(cur,old)['reason'],'open_time_bucket')
    def test_unknown_preview_not_empty_preview(self):self.assertEqual(self.decide(preview_observed=False)['reason'],'missing_preview_observation')
    def test_excluded_skipped(self):self.assertEqual(self.decide(authorized=False)['result'],'skip')
    def test_weekly_label_not_same_week_across_seven_days(self):
        cur,old=self.pair(displayed_time='星期六',observed_at='2026-11-23T08:00:00+08:00')
        self.assertEqual(checks.chat_decision(cur,old)['reason'],'time_changed')
    def test_midnight_year_rollover(self):
        win=checks.qq_time_window('12/31','2027-01-01T08:00:00+08:00')
        self.assertEqual(win[0].date().isoformat(),'2026-12-31')
    def test_invalid_date_not_crash(self):self.assertIsNone(checks.qq_time_window('2/30','2026-03-01T08:00:00+08:00'))

if __name__=='__main__':unittest.main()
