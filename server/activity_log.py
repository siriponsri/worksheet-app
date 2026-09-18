"""Who opened the workspace, and who printed which controlled document.

Why this exists
---------------
QA asked three questions. Two of them belong here:

  1. who printed a controlled document, and when
  2. who used this workspace at all

The third — who entered the data — is answered on the Google Sheets side by the
bound Apps Script sync, not here.

What this is, and what it is NOT
--------------------------------
The operator identifies themselves with their employee number. Nothing checks
that claim, so this is **attribution, not authentication**: it records who said
they were at the machine, exactly as a paper issue logbook does. It is not a
21 CFR Part 11 electronic signature and must never be described as one. Part 11
§ 11.10(d) and (g) want authenticated, access-limited entry; that needs an
identity system this laboratory does not have on these machines yet.

What it does give QA that they did not have:

  * a **server-generated** timestamp — the browser cannot set it, which is the
    part of § 11.10(e) this can honestly satisfy
  * an **append-only** file: entries are only ever added, never rewritten
  * the worksheet number and the controlled template each printed document used

The file lives on the configured project share as ``activity-log.jsonl`` — one
JSON object per line, so it can be appended safely, read with any text editor,
and never silently rewritten by a spreadsheet.

Forwarding to the System DB
---------------------------
Optional, off by default, and configured **only on the server**. If
``server/log-forward.json`` supplies the System DB Web App URL and the sync
token, each entry is also appended to that spreadsheet's ``logs`` tab. The
token stays in that file on this machine: it is never sent to the browser,
never compiled into the bundle, and never returned by any endpoint here.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime, timezone

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore


def _lock_file(handle):
    """Best-effort cross-process exclusive lock for the open file handle."""
    if msvcrt is None:
        return
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    except OSError:
        pass


def _unlock_file(handle):
    """Release a lock obtained by _lock_file."""
    if msvcrt is None:
        return
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_SHARE_ROOT = os.environ.get('ANF3_PROJECT_SHARE', '').strip()
LOG_PATH = os.path.join(PROJECT_SHARE_ROOT, 'activity-log.jsonl') if PROJECT_SHARE_ROOT else ''
FORWARD_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log-forward.json')

# Only these actions are accepted. An unknown action is rejected rather than
# stored, so the log cannot be used as a general write channel by the browser.
ACTIONS = {
    'workspace_opened',   # the app was opened in a browser
    'record_opened',      # a worksheet was read
    'pdf_generated',      # a controlled document was rendered
    'pdf_printed',        # the print dialog was opened for one
    'pdf_downloaded',     # the file was saved
    'pdf_batch',          # several worksheets were merged and printed together
    'operator_changed',   # somebody else took over the machine
    'backup_succeeded',    # a generated artifact reached the project share
    'backup_failed',       # local generation succeeded but share backup did not
    'backup_retried',      # a pending share backup was attempted again
}

_WRITE_LOCK = threading.Lock()
_MAX_FIELD = 200


def configure_project_share(root):
    """Point persistent logging at the same central root as document storage."""
    global PROJECT_SHARE_ROOT, LOG_PATH
    PROJECT_SHARE_ROOT = str(root or '').strip()
    LOG_PATH = os.path.join(PROJECT_SHARE_ROOT, 'activity-log.jsonl') if PROJECT_SHARE_ROOT else ''


def _clean(value, limit=_MAX_FIELD):
    """One line, bounded length. Log fields are evidence, not free storage."""
    text = str(value if value is not None else '').replace('\r', ' ').replace('\n', ' ').strip()
    return text[:limit]


def _forward_config():
    try:
        with open(FORWARD_CONFIG, 'r', encoding='utf-8') as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        return None
    url = str(config.get('systemUrl') or '').strip()
    token = str(config.get('syncToken') or '').strip()
    if not url.startswith('https://script.google.com/') or not token:
        return None
    return {'url': url, 'token': token, 'domain': str(config.get('domain') or 'air').strip()}


def _forward(entry):
    """Best effort. A spreadsheet that cannot be reached must never stop a print."""
    config = _forward_config()
    if not config:
        return
    try:
        import urllib.request
        payload = json.dumps({
            'action': 'log',
            'token': config['token'],
            'domain': config['domain'],
            'log': {
                'action': entry['action'].upper(),
                'worksheetNo': entry.get('worksheetNo', ''),
                # The sheet's `username` column gets the readable form, the
                # same shape the owner asked for after seeing what free-text
                # names alone did to `createdBy`.
                'username': entry.get('operator', ''),
                'operatorName': entry.get('operatorName', ''),
                'operatorCode': entry.get('operatorCode', ''),
                'details': f"{entry.get('detail', '')} host={entry.get('host', '')}".strip(),
            },
        }).encode('utf-8')
        request = urllib.request.Request(
            config['url'], data=payload,
            headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.urlopen(request, timeout=6).read()
    except Exception:  # noqa: BLE001 - forwarding is never load-bearing
        pass


def record(action, operator='', worksheet_no='', detail='', operator_name='', operator_code=''):
    """Append one entry. Returns it, or None when the action is not recognised.

    ``operator`` is the display form ("สมชาย ใจดี (4417)"); ``operator_name``
    and ``operator_code`` are kept separately so the log can be filtered by
    code — a name alone is what left the System DB's own ``createdBy`` column
    unanswerable, holding ``na``, ``KC`` and ``kulwanee`` for the same kind of
    fact.
    """
    if action not in ACTIONS:
        return None, 'UNKNOWN_ACTION'
    entry = {
        # The server's clock, in UTC with an offset, so entries from different
        # machines can be ordered against each other.
        'at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
        'action': action,
        'operator': _clean(operator, 100),
        'operatorName': _clean(operator_name, 60),
        'operatorCode': _clean(operator_code, 40),
        'worksheetNo': _clean(worksheet_no, 60),
        'detail': _clean(detail),
        'host': _clean(socket.gethostname(), 60),
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _WRITE_LOCK:
        if not LOG_PATH:
            return None, 'SHARE_UNAVAILABLE'
        try:
            with open(LOG_PATH, 'a', encoding='utf-8') as handle:
                _lock_file(handle)
                try:
                    handle.write(line + '\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                finally:
                    _unlock_file(handle)
        except OSError:
            return None, 'WRITE_FAILED'
    threading.Thread(target=_forward, args=(entry,), daemon=True).start()
    return entry, None


def read(limit=500):
    """The most recent entries, newest first."""
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as handle:
            lines = handle.readlines()
    except OSError:
        return []
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue  # a torn line is skipped, never repaired in place
    entries.reverse()
    return entries


def as_csv(limit=5000):
    """For handing to QA. Excel-friendly, quoted, newest first."""
    rows = ['at,action,operatorName,operatorCode,operator,worksheetNo,detail,host']
    for entry in read(limit):
        cells = [entry.get(key, '') for key in
                 ('at', 'action', 'operatorName', 'operatorCode', 'operator', 'worksheetNo', 'detail', 'host')]
        rows.append(','.join('"' + str(cell).replace('"', '""') + '"' for cell in cells))
    return '\n'.join(rows)


def forwarding_enabled():
    return _forward_config() is not None
