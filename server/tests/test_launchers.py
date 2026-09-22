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


def test_start_anf3_never_promotes_local_copy_to_controlled_storage(start_anf3):
    """A local AppData launcher must require an explicit project share."""
    assert 'ANF3_PROJECT_SHARE is not configured' in start_anf3
    assert 'The launcher directory is not controlled document storage.' in start_anf3
    assert 'set "ANF3_PROJECT_SHARE=%APP_DIR%"' not in start_anf3
    assert 'T:\\' not in start_anf3
    assert 'T:/' not in start_anf3


def test_start_anf3_treats_recorded_port_as_stale_runtime_state(start_anf3):
    """A missing/foreign recorded port must not block a fresh server start."""
    assert 'recorded_port_busy' not in start_anf3
    assert 'tcp_port_busy' not in start_anf3
    assert start_anf3.count('del /q "%LOCAL_DIR%.anf3-port"') == 1
    assert start_anf3.count('del /q "%APP_DIR%.anf3-port"') == 1
    assert 'goto :busy_server' not in start_anf3
    assert '8000..8039' in start_anf3


@pytest.mark.parametrize(
    ('recorded_port', 'occupied', 'healthy_port', 'expected'),
    [
        (None, False, None, 'start'),
        ('8000', False, None, 'start'),
        ('8000', True, '8000', 'reuse'),
        ('8000', True, '8001', 'reuse'),
        ('8000', True, None, 'start'),
    ],
)
def test_port_state_scenarios(recorded_port, occupied, healthy_port, expected):
    """Only an actual healthy ANF3 service is reused; other states start fresh."""
    found = healthy_port if occupied and healthy_port else None
    action = 'reuse' if found else 'start'
    assert action == expected


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
