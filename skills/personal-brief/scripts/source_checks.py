#!/usr/bin/env python3
"""Read-only source checks. Decisions describe coverage, never message meaning."""
import argparse
import hashlib
import json
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


def chat_decision(current, previous=None):
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
