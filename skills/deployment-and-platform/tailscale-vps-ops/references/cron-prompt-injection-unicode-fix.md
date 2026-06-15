# Cron Prompt Injection: Invisible Unicode Fix

Use this when a Hermes cron job is blocked by prompt-injection scanning because upstream data introduced invisible Unicode characters.

## Typical Symptom

```
BLOCKED
The assembled prompt tripped the cron injection scanner.
Scanner result: prompt contains invisible unicode U+200C.
```

## Root Cause

Usually the prompt template itself is fine.

The real source is often upstream data that was scraped, fetched from RSS, or read from an API, then written into a JSON or text artifact that later got injected into the assembled prompt.

## Investigation Order

1. Check the job definition or prompt template
2. Check the script that feeds prompt context
3. Check the generated data files that the script wrote

The generated data file is often the actual culprit.

## Handy Checks

```bash
python3 -c "
import json
job = [x for x in json.load(open('~/.hermes/cron/jobs.json')) if x['id']=='<JOB_ID>'][0]
print('U+200C in prompt:', job['prompt'].count('\u200c'))
"
```

```bash
python3 -c "
s = open('~/.hermes/scripts/<script>.py').read()
print('U+200C in script:', s.count('\u200c'))
"
```

```bash
python3 -c "
s = open('<generated-data-file>').read()
hits = [i for i, ch in enumerate(s) if ch == '\u200c']
print(f'Found {len(hits)} U+200C characters')
[print(f'  pos {i}: {repr(s[max(0, i-30):i+30])}') for i in hits[:5]]
"
```

## Fast Cleanup

```bash
python3 -c "
path = '<generated-data-file>'
s = open(path).read()
cleaned = s.replace('\u200c', '').replace('\u200b', '')
if s != cleaned:
    open(path, 'w').write(cleaned)
    print('cleaned invisible unicode from', path)
"
```

## Durable Fix

Clean payloads before writing them:

```python
import re

_INVISIBLE_UNICODE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")

def _clean_obj(obj):
    if isinstance(obj, str):
        return _INVISIBLE_UNICODE.sub("", obj)
    if isinstance(obj, list):
        return [_clean_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _clean_obj(v) for k, v in obj.items()}
    return obj

payload = _clean_obj(payload)
```

## Validate The Fix

```bash
python3 -c "
s = open('<generated-data-file>').read()
print('U+200C count:', s.count('\u200c'))
"
```

```bash
python3 -m py_compile ~/.hermes/scripts/<script>.py
```

## Common Invisible Characters

- `\u200b` zero-width space
- `\u200c` zero-width non-joiner
- `\u200d` zero-width joiner
- `\u2060` word joiner
- `\ufeff` byte-order mark
