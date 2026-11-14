#!/usr/bin/env python3
"""Validate event time serialization, not the truth of the source evidence."""
import argparse
from datetime import date, datetime
import json
from pathlib import Path
import re

FIELDS = {'source_time', 'observed_at', 'message_time', 'quoted_source_time'}
REQUIRED = {'source_time', 'observed_at'}


def time_error(value, field):
    if value == 'unknown':
        return 'observation_time_required' if field == 'observed_at' else None
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            date.fromisoformat(value)
            return 'observation_needs_time_and_zone' if field == 'observed_at' else None
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if instant.tzinfo is None or instant.utcoffset() is None:
            return 'datetime_needs_timezone'
    except ValueError:
        return 'invalid_iso_date_or_datetime'
    return None


def validate(text):
    errors, seen, fields = [], set(), set()
    event, start = None, 0

    def finish():
        if event:
            for field in sorted(REQUIRED - fields):
                errors.append(dict(event=event, line=start, field=field, error='missing_field'))

    for line_no, line in enumerate(text.splitlines(), 1):
        if line.startswith('## EVT-'):
            finish()
            event = re.split(r'[｜|\s]', line[3:].strip(), maxsplit=1)[0]
            start, fields = line_no, set()
            if event in seen:
                errors.append(dict(event=event, line=line_no, error='duplicate_event_id'))
            seen.add(event)
        match = re.match(r'^- ([a-z_]+):\s*(.*?)\s*$', line)
        if event and match and match[1] in FIELDS:
            field, value = match[1], match[2]
            if field in fields:
                errors.append(dict(event=event, line=line_no, field=field, error='duplicate_field'))
            fields.add(field)
            error = time_error(value, field)
            if error:
                errors.append(dict(event=event, line=line_no, field=field, error=error))
    finish()
    return dict(valid=not errors, event_count=len(seen), errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', type=Path)
    args = parser.parse_args()
    result = validate(args.events.read_text(encoding='utf-8'))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
