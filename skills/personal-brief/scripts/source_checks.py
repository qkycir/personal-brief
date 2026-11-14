#!/usr/bin/env python3
"""Read-only source checks. Decisions describe coverage, never message meaning."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path


def transcript_probe(path, previous=None, recording=False):
    previous = previous or {}
    path = Path(path)
    try:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        return {"result": "pending", "reason": type(exc).__name__}
    digest = hashlib.sha256(data).hexdigest()
    result = {"observed_sha256": digest, "size": len(data)}
    if recording or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        result.update(result="pending", reason="recording_or_changing")
    elif not data.strip():
        result.update(result="pending", reason="empty")
    elif previous.get("content_sha256") != digest or previous.get("processing_state") == "pending":
        result.update(result="needs_read", reason="new_changed_or_unprocessed")
    else:
        result.update(result="unchanged", reason="matches_processed_content")
    return result


def qq_time_window(label, observed_at):
    """Resolve a visible QQ time label at the time it was observed; end is exclusive."""
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return None
        label = re.sub(r"\s+", "", label)
        match = re.fullmatch(r"(.*?)(\d{1,2}):(\d{2})", label)
        day_label = match[1] if match else label
        base = observed.replace(hour=0, minute=0, second=0, microsecond=0)
        if day_label in ("", "今天", "昨天", "前天"):
            base -= timedelta(days={"":0,"今天":0,"昨天":1,"前天":2}[day_label])
        elif re.fullmatch(r"(?:星期|周)[一二三四五六日天]", day_label):
            weekday = "一二三四五六日".index(day_label[-1].replace("天", "日"))
            base -= timedelta(days=(base.weekday()-weekday) % 7)
        elif re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", day_label):
            y,m,d=map(int,re.split(r"[-/]",day_label));base=base.replace(year=y,month=m,day=d)
        elif re.fullmatch(r"\d{1,2}/\d{1,2}", day_label):
            m,d=map(int,day_label.split('/'));base=base.replace(month=m,day=d)
            if base > observed:base=base.replace(year=base.year-1)
        else:
            return None
        if match:
            base=base.replace(hour=int(match[2]),minute=int(match[3]))
        end=base+timedelta(minutes=1) if match else base+timedelta(days=1)
        if base > observed:return None
        return base,end
    except (ValueError,TypeError,AttributeError):
        return None


def qq_increment_decision(current, previous=None):
    """Compare with a previously accepted list snapshot, not a body-coverage claim."""
    def result(value,reason):return {"result":value,"reason":reason}
    if current.get('authorized') is not True:return result('skip','outside_scope')
    if current.get('identity_match') not in ('stable_id','unique_local'):
        return result('needs_read','identity_uncertain')
    key=current.get('identity_key')
    previous=previous or {}
    accepted=previous.get('accepted_list_observation')
    if not key or not isinstance(accepted,dict):return result('needs_read','no_accepted_snapshot')
    if accepted.get('identity_key')!=key:return result('needs_read','identity_changed')
    if previous.get('pending_incremental') is True:return result('needs_read','unprocessed_increment')
    if accepted.get('acceptance') not in ('body_checked','initial_list_baseline'):
        return result('needs_read','snapshot_not_accepted')
    if current.get('change_signal') is True:return result('needs_read','new_activity_signal')
    if current.get('preview_observed') is not True or accepted.get('preview_observed') is not True:
        return result('needs_read','missing_preview_observation')
    if not isinstance(current.get('preview'),str) or not isinstance(accepted.get('preview'),str):
        return result('needs_read','missing_preview_observation')
    if (current['preview'],current.get('preview_kind')) != (accepted['preview'],accepted.get('preview_kind')):
        return result('needs_read','preview_changed')
    # A changed unread count is useful; unchanged unread is never the sole criterion.
    if (current.get('unread_count') is not None and accepted.get('unread_count') is not None
            and current['unread_count']>accepted['unread_count']):
        return result('needs_read','unread_increased')
    old=qq_time_window(accepted.get('displayed_time'),accepted.get('observed_at'))
    new=qq_time_window(current.get('displayed_time'),current.get('observed_at'))
    if not old or not new:return result('needs_read','unresolved_time')
    if max(old[0],new[0])>=min(old[1],new[1]):return result('needs_read','time_changed')
    # Both observations must be after their displayed interval closed. An ongoing
    # day or minute can hide another identical/truncated/type-only message.
    prior_at=datetime.fromisoformat(accepted['observed_at'].replace('Z','+00:00'))
    now_at=datetime.fromisoformat(current['observed_at'].replace('Z','+00:00'))
    if prior_at < old[1] or now_at < new[1]:return result('needs_read','open_time_bucket')
    if now_at < prior_at:return result('needs_read','observation_order')
    return result('unchanged','same_accepted_list_observation')


def chat_decision(current, previous=None):
    if current.get('source') == 'QQ':
        return qq_increment_decision(current, previous)
    previous = previous or {}
    if current.get("authorized") is not True:
        return {"result": "skip", "reason": "outside_scope"}
    if current.get("identity_status") != "confirmed":
        return {"result": "needs_read", "reason": "identity_uncertain"}
    if (current.get("preview_complete") is not True or current.get("preview_kind") != "text"
            or current.get("time_precise") is not True):
        return {"result": "needs_read", "reason": "ambiguous_preview_or_time"}
    if not previous or previous.get("body_verified") is not True:
        return {"result": "needs_read", "reason": "no_verified_boundary"}
    # Equal minute labels cannot rule out another message in that same minute.
    if current.get("observation_after_displayed_minute") is not True:
        return {"result": "needs_read", "reason": "same_minute_possible"}
    if any(current.get(k) != previous.get(k) for k in ("identity_key", "displayed_time", "preview")):
        return {"result": "needs_read", "reason": "changed"}
    if not current.get("identity_key") or not current.get("preview"):
        return {"result": "needs_read", "reason": "missing_evidence"}
    return {"result": "unchanged", "reason": "comparable_list_observation"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    t = sub.add_parser("transcript")
    t.add_argument("path"); t.add_argument("--previous", help="JSON source record")
    t.add_argument("--recording", action="store_true")
    c = sub.add_parser("chat")
    c.add_argument("current", help="JSON observation"); c.add_argument("--previous")
    a = p.parse_args()
    previous = json.loads(Path(a.previous).read_text()) if a.previous else None
    result = (transcript_probe(a.path, previous, a.recording) if a.mode == "transcript"
              else chat_decision(json.loads(Path(a.current).read_text()), previous))
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__": main()
