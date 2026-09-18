import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def start_anf3():
    return (ROOT / 'START-ANF3.bat').read_text(encoding='utf-8')


@pytest.fixture()
def start_server():
    return (ROOT / 'START-SERVER.bat').read_text(encoding='utf-8')


def test_start_anf3_derives_share_root_without_hard_coded_drive(start_anf3):
    """The launcher must derive the durable share root from its own directory
    so it works with any mapped drive letter, username, or path containing spaces."""
    assert 'set "SHARE_ROOT=%~dp0"' in start_anf3
    assert 'set "ANF3_PROJECT_SHARE=%SHARE_ROOT%"' in start_anf3 or 'set "ANF3_PROJECT_SHARE=%~dp0"' in start_anf3
    assert 'T:\\' not in start_anf3
    assert 'T:/' not in start_anf3


def test_start_anf3_here_mode_requires_explicit_share(start_anf3):
    """Developer /here mode must receive ANF3_PROJECT_SHARE explicitly; the
    local repo must not silently become durable storage."""
    here_block_match = re.search(r'if /i "%~1"=="/here" \((.*?)\n\)', start_anf3, re.DOTALL | re.IGNORECASE)
    assert here_block_match, 'START-ANF3.bat must have a /here block'
    here_block = here_block_match.group(1)
    assert 'ANF3_PROJECT_SHARE' in here_block
    assert 'exit /b 1' in here_block


def test_start_anf3_sets_share_before_starting_server(start_anf3):
    """Every path that starts START-SERVER.bat must first define ANF3_PROJECT_SHARE.

    The variable is set in :run_here_locked right before the `start` command.
    """
    locked_match = re.search(r':run_here_locked\s+(.*?)start "ANF3 Local Server"', start_anf3, re.DOTALL | re.IGNORECASE)
    assert locked_match, ':run_here_locked must exist and start the server'
    locked_block = locked_match.group(1)
    assert 'ANF3_PROJECT_SHARE' in locked_block


def test_start_server_requires_inherited_share_root(start_server):
    """START-SERVER.bat must refuse to start if ANF3_PROJECT_SHARE is missing.

    It must not hard-code a drive letter or fall back to LOCALAPPDATA.
    """
    assert 'if not defined ANF3_PROJECT_SHARE' in start_server
    assert 'exit /b 1' in start_server
    assert 'T:\\' not in start_server
    assert 'T:/' not in start_server
    assert 'LOCALAPPDATA' not in start_server


def test_server_and_log_module_have_no_hard_coded_share():
    """The Python modules must read the share root from the environment only."""
    pdf_server = (ROOT / 'server' / 'pdf_server.py').read_text(encoding='utf-8')
    activity_log = (ROOT / 'server' / 'activity_log.py').read_text(encoding='utf-8')
    for source, name in ((pdf_server, 'pdf_server.py'), (activity_log, 'activity_log.py')):
        assert 'T:\\' not in source, f'{name} contains a hard-coded T: drive'
        assert 'T:/' not in source, f'{name} contains a hard-coded T: drive'
        assert 'AN_Share' not in source, f'{name} contains a hard-coded share path'
        assert r'ANF3_PROJECT_SHARE' in source, f'{name} must read ANF3_PROJECT_SHARE from environment'
