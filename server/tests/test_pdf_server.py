import json
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pdf_server


@pytest.fixture()
def client(tmp_path, monkeypatch):
    template_dir = tmp_path / 'templates'
    cache_dir = tmp_path / 'cache'
    words_dir = cache_dir / 'words'
    pdfs_dir = cache_dir / 'pdfs'
    share_dir = tmp_path / 'project-share'
    template_dir.mkdir()
    words_dir.mkdir(parents=True)
    pdfs_dir.mkdir(parents=True)
    desktop_dir = tmp_path / 'home' / 'Desktop'
    desktop_dir.mkdir(parents=True)
    for template_name in pdf_server.WORKFLOW_TEMPLATES.values():
        (template_dir / template_name).write_bytes(b'template-' + template_name.encode())

    monkeypatch.setattr(pdf_server, 'TEMPLATE_DIR', str(template_dir))
    monkeypatch.setattr(pdf_server, 'WORDS_DIR', str(words_dir))
    monkeypatch.setattr(pdf_server, 'PDFS_DIR', str(pdfs_dir))
    monkeypatch.setattr(pdf_server, 'PROJECT_SHARE_ROOT', str(share_dir))
    monkeypatch.setattr(pdf_server, 'BACKUP_SPOOL_DIR', str(tmp_path / 'pending'))
    pdf_server.activity_log.configure_project_share(str(share_dir))
    monkeypatch.setattr(pdf_server.os.path, 'expanduser', lambda _value: str(tmp_path / 'home'))

    def fake_word(_template_path, output_path, _data):
        with zipfile.ZipFile(output_path, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document><w:body><w:p><w:r><w:t>filled</w:t></w:r></w:p></w:body></w:document>')
        return 1

    def fake_multipage(_template_path, output_path, pages):
        with zipfile.ZipFile(output_path, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document><w:body><w:p><w:r><w:t>filled</w:t></w:r></w:p></w:body></w:document>')
        return len(pages)

    def fake_convert(_word_path, pdf_path):
        Path(pdf_path).write_bytes(b'%PDF-1.4 test\n%%EOF\n')
        return True, 'test converter', None

    monkeypatch.setattr(pdf_server, 'replace_placeholders_in_file', fake_word)
    monkeypatch.setattr(pdf_server, 'build_multipage_docx', fake_multipage)
    monkeypatch.setattr(pdf_server, 'convert_to_pdf', fake_convert)
    pdf_server.app.config.update(TESTING=True)
    return pdf_server.app.test_client()


def test_pdf_id_lifecycle_and_content_template_cache(client, monkeypatch):
    payload = {
        'workflow': 'pw-prw',
        'worksheetNo': 'PW-26-0001',
        'templateName': '../../untrusted.docx',
        'data': {'analyst': 'A'}
    }
    first = client.post('/api/pdfs', json=payload)
    assert first.status_code == 201
    created = first.get_json()
    assert len(created['pdfId']) == 64
    assert created['cached'] is False

    second = client.post('/api/pdfs', json=payload)
    assert second.status_code == 200
    assert second.get_json() == {**created, 'cached': True}

    metadata = client.get(f"/api/pdfs/{created['pdfId']}")
    assert metadata.status_code == 200
    assert metadata.get_json()['filename'] == 'PW-26-0001.pdf'
    assert str(pdf_server.PDFS_DIR) not in metadata.get_data(as_text=True)

    download = client.get(f"/api/pdfs/{created['pdfId']}/download")
    assert download.status_code == 200
    assert download.mimetype == 'application/pdf'

    inline = client.get(f"/api/pdfs/{created['pdfId']}/download?inline=1")
    assert inline.status_code == 200
    assert 'inline' in inline.headers['Content-Disposition']

    saved = client.post(f"/api/pdfs/{created['pdfId']}/save-desktop", json={})
    assert saved.status_code == 410


def test_project_share_backup_is_hash_verified_and_idempotent(client, tmp_path, monkeypatch):
    share = tmp_path / 'project-share'
    spool = tmp_path / 'pending'
    monkeypatch.setattr(pdf_server, 'PROJECT_SHARE_ROOT', str(share))
    monkeypatch.setattr(pdf_server, 'BACKUP_SPOOL_DIR', str(spool))
    monkeypatch.setattr(pdf_server.activity_log, 'record', lambda **_kwargs: ({'action': 'test'}, None))
    payload = {'workflow': 'pw-prw', 'worksheetNo': 'PW-26-0090', 'data': {'analyst': 'A'}}

    first = client.post('/api/pdfs', json=payload)
    assert first.status_code == 201
    body = first.get_json()
    assert body['backup']['status'] == 'succeeded'
    pdf_id = body['pdfId']
    share_pdf = share / 'pdfs' / 'pw-prw' / 'PW-26-0090.pdf'
    share_word = share / 'words' / 'pw-prw' / 'PW-26-0090.docx'
    share_manifest = share / 'manifests' / 'pw-prw' / 'PW-26-0090' / 'PW-26-0090.json'
    assert share_pdf.stat().st_size > 0
    assert share_word.stat().st_size > 0
    assert share_manifest.is_file()

    second = client.post('/api/pdfs', json=payload)
    assert second.status_code == 200
    assert second.get_json()['backup']['status'] == 'succeeded'
    assert not list(spool.glob('*.json'))


def test_project_share_replacement_keeps_old_version_in_history(client, tmp_path, monkeypatch):
    share = tmp_path / 'project-share'
    monkeypatch.setattr(pdf_server, 'PROJECT_SHARE_ROOT', str(share))
    monkeypatch.setattr(pdf_server.activity_log, 'record', lambda **_kwargs: ({'action': 'test'}, None))
    initial = {'workflow': 'pw-prw', 'worksheetNo': 'PW-26-0093', 'data': {'analyst': 'A'}}
    first = client.post('/api/pdfs', json=initial)
    assert first.status_code == 201
    old_pdf_id = first.get_json()['pdfId']

    changed = {**initial, 'data': {'analyst': 'B'}}
    conflict = client.post('/api/pdfs', json=changed).get_json()
    replacement = client.post('/api/pdfs', json={**changed, 'regeneration': {
        'mode': 'replace', 'requestedPdfId': conflict['requestedPdfId'],
        'existingPdfIds': conflict['existingPdfIds']
    }})
    assert replacement.status_code == 201
    assert replacement.get_json()['backup']['status'] == 'succeeded'
    history = share / 'history' / 'pw-prw' / 'PW-26-0093' / old_pdf_id
    assert (history / 'PW-26-0093.json').is_file()
    assert (share / 'pdfs' / 'pw-prw' / 'PW-26-0093.pdf').is_file()


def test_project_share_outage_does_not_leave_local_controlled_artifacts(client, tmp_path, monkeypatch):
    blocked = tmp_path / 'share-is-a-file'
    blocked.write_text('unavailable', encoding='utf-8')
    share = tmp_path / 'project-share'
    monkeypatch.setattr(pdf_server, 'PROJECT_SHARE_ROOT', str(blocked))
    monkeypatch.setattr(pdf_server.activity_log, 'record', lambda **_kwargs: ({'action': 'test'}, None))
    payload = {'workflow': 'pw-prw', 'worksheetNo': 'PW-26-0091', 'data': {'analyst': 'A'}}

    created = client.post('/api/pdfs', json=payload)
    assert created.status_code == 503
    assert not [path for path in (tmp_path / 'cache').rglob('*') if path.is_file()]


def test_project_share_replaces_corrupt_primary_for_same_content(client, tmp_path, monkeypatch):
    share = tmp_path / 'project-share'
    monkeypatch.setattr(pdf_server, 'PROJECT_SHARE_ROOT', str(share))
    monkeypatch.setattr(pdf_server.activity_log, 'record', lambda **_kwargs: ({'action': 'test'}, None))
    payload = {'workflow': 'pw-prw', 'worksheetNo': 'PW-26-0092', 'data': {'analyst': 'A'}}
    created = client.post('/api/pdfs', json=payload).get_json()
    pdf_id = created['pdfId']
    destination = share / 'pdfs' / 'pw-prw' / 'PW-26-0092.pdf'
    destination.write_bytes(b'%PDF-1.4 different\n%%EOF\n')

    cached = client.post('/api/pdfs', json=payload)
    assert cached.status_code == 201
    assert cached.get_json()['cached'] is False
    assert destination.read_bytes().startswith(b'%PDF-')


def test_torn_artifact_set_is_detected_and_regenerated(client, tmp_path, monkeypatch):
    """A partial/crashed promotion that leaves DOCX+PDF valid but metadata stale,
    or metadata present with mismatched artifact hashes, must never be treated
    as the current worksheet version."""
    share = tmp_path / 'project-share'
    monkeypatch.setattr(pdf_server, 'PROJECT_SHARE_ROOT', str(share))
    monkeypatch.setattr(pdf_server.activity_log, 'record', lambda **_kwargs: ({'action': 'test'}, None))
    payload = {'workflow': 'pw-prw', 'worksheetNo': 'PW-26-0094', 'data': {'analyst': 'A'}}
    created = client.post('/api/pdfs', json=payload).get_json()
    pdf_id = created['pdfId']

    # Tear the set: keep metadata but replace DOCX with different content.
    word_path = share / 'words' / 'pw-prw' / 'PW-26-0094.docx'
    pdf_path = share / 'pdfs' / 'pw-prw' / 'PW-26-0094.pdf'
    metadata_path = share / 'manifests' / 'pw-prw' / 'PW-26-0094' / 'PW-26-0094.json'
    assert word_path.is_file() and pdf_path.is_file() and metadata_path.is_file()

    with zipfile.ZipFile(word_path, 'a') as archive:
        archive.writestr('extra.xml', b'<torn>different content</torn>')

    # Same input must now regenerate because the stored DOCX hash no longer
    # matches the metadata commit record.
    regenerated = client.post('/api/pdfs', json=payload)
    assert regenerated.status_code == 201
    assert regenerated.get_json()['cached'] is False

    # A changed input must still surface a controlled conflict, not silently
    # overwrite the torn set.
    changed = {**payload, 'data': {'analyst': 'B'}}
    conflict = client.post('/api/pdfs', json=changed).get_json()
    assert conflict['code'] == 'WORKSHEET_CONTENT_CONFLICT'


def test_rejects_unknown_workflow_paths_and_validates_cv_routes(client):
    unknown = client.post('/api/pdfs', json={'workflow': '../pdfs', 'data': {}})
    assert unknown.status_code == 400

    missing_method = client.post('/api/pdfs', json={
        'workflow': 'cleaning-validation-rinse-pour',
        'worksheetNo': 'CVR-1',
        'data': {'sampleMatrix': 'Rinse'}
    })
    assert missing_method.status_code == 422

    valid_rinse = client.post('/api/pdfs', json={
        'workflow': 'cleaning-validation-rinse-pour',
        'worksheetNo': 'CVR-1',
        'cvContext': {'samplingFamily': 'Rinse', 'testMethod': 'Pour Plate'},
        'data': {'sampleMatrix': 'Rinse'}
    })
    assert valid_rinse.status_code == 201
    assert valid_rinse.get_json()['pdfId']

    wrong_family = client.post('/api/pdfs', json={
        'workflow': 'cleaning-validation-contact',
        'worksheetNo': 'CV-1',
        'data': {'sampleMatrix': 'Rinse'}
    })
    assert wrong_family.status_code == 422

    assert client.get('/api/pdfs/../../templates/a').status_code == 404
    assert client.get('/server/pdf_server.py').status_code == 404
    assert client.get('/C:/Windows/win.ini').status_code == 404
    assert client.post('/api/pdfs', json={
        'workflow': 'pw-prw', 'worksheetNo': 'CON', 'data': {}
    }).status_code == 400


def test_pdf_capabilities_keep_cv_routes_explicit_and_safe(client):
    response = client.get('/api/pdf-capabilities')
    assert response.status_code == 200
    capabilities = {item['workflow']: item for item in response.get_json()['capabilities']}
    assert capabilities['cleaning-validation-rinse-pour']['owner'] == 'cv'
    assert capabilities['cleaning-validation-rinse-pour']['sourceWorkflow'] == 'pw-prw'
    assert capabilities['cleaning-validation-rinse-membrane']['sourceWorkflow'] == 'wfi-pus'
    assert 'path' not in response.get_data(as_text=True).lower()


def test_legacy_path_apis_are_gone(client):
    assert client.post('/api/convert-word-to-pdf', json={
        'wordPath': 'C:/secret.docx'
    }).status_code == 410
    assert client.get('/api/list-files').status_code == 410


def test_request_limit_and_catalog(client):
    response = client.post(
        '/api/pdfs',
        data=json.dumps({'workflow': 'pw-prw', 'data': {'value': 'x' * (2 * 1024 * 1024)}}),
        content_type='application/json'
    )
    assert response.status_code == 413

    catalog = client.get('/api/catalog/status').get_json()
    assert catalog['pdfUrl'] == '/inventory_catalog.pdf'
    assert catalog['indexUrl'] == '/catalog/inventory-index.json'
    assert catalog['hashMatches'] is True
    assert catalog['indexAvailable'] is True
    assert catalog['rowCount'] == 95
    assert client.get(catalog['indexUrl']).status_code == 200


def test_forged_sidecar_cannot_control_download_or_desktop_path(client):
    created = client.post('/api/pdfs', json={
        'workflow': 'pw-prw', 'worksheetNo': 'PW-1', 'data': {}
    }).get_json()
    metadata_path = (Path(pdf_server.PROJECT_SHARE_ROOT) / 'manifests' / 'pw-prw' /
                     'PW-1' / 'PW-1.json')
    metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
    metadata['filename'] = '../outside.pdf'
    Path(metadata_path).write_text(json.dumps(metadata), encoding='utf-8')

    assert client.get(f"/api/pdfs/{created['pdfId']}").status_code == 404
    assert client.post(f"/api/pdfs/{created['pdfId']}/save-desktop").status_code == 410


def test_malformed_catalog_manifest_fails_closed(client, tmp_path, monkeypatch):
    malformed = tmp_path / 'inventory-index.json'
    malformed.write_text('{broken', encoding='utf-8')
    monkeypatch.setattr(pdf_server, 'INVENTORY_INDEX_PATHS', (str(malformed),))

    response = client.get('/api/catalog/status')
    assert response.status_code == 200
    assert response.get_json()['indexAvailable'] is False


def test_word_timeout_only_targets_recorded_winword_pid(tmp_path, monkeypatch):
    word_path = tmp_path / 'input.docx'
    pdf_path = tmp_path / 'output.pdf'
    word_path.write_bytes(b'word')
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if '-File' in command:
            Path(str(word_path) + '.word.pid').write_text('1234', encoding='ascii')
            raise subprocess.TimeoutExpired(command, 60)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pdf_server.subprocess, 'run', fake_run)
    success, error = pdf_server.convert_with_word(str(word_path), str(pdf_path))

    assert success is False
    assert 'timeout' in error.lower()
    cleanup = ' '.join(calls[-1])
    assert '1234' in cleanup
    assert 'WINWORD' in cleanup
    assert 'taskkill' not in cleanup.lower()


def test_broken_word_is_disabled_and_libreoffice_handles_future_requests(tmp_path, monkeypatch):
    word_path = tmp_path / 'input.docx'
    pdf_path = tmp_path / 'output.pdf'
    word_path.write_bytes(b'word')
    calls = []

    def broken_word(_word, _pdf):
        calls.append('word')
        return False, 'Cannot convert null to System.IntPtr'

    def libreoffice(_word, output_dir):
        calls.append('libreoffice')
        (Path(output_dir) / 'input.pdf').write_bytes(b'%PDF')
        return True, None

    monkeypatch.setattr(pdf_server, 'MS_OFFICE_AVAILABLE', True)
    monkeypatch.setattr(pdf_server, 'LIBREOFFICE_PATH', 'soffice')
    monkeypatch.setattr(pdf_server, 'convert_with_word', broken_word)
    monkeypatch.setattr(pdf_server, 'convert_with_libreoffice', libreoffice)

    assert pdf_server._try_convert(str(word_path), str(pdf_path))[:2] == (True, 'LibreOffice')
    assert calls == ['word', 'libreoffice']
    assert pdf_server.MS_OFFICE_AVAILABLE is False
    pdf_path.unlink()
    assert pdf_server._try_convert(str(word_path), str(pdf_path))[:2] == (True, 'LibreOffice')
    assert calls == ['word', 'libreoffice', 'libreoffice']


def test_converter_selection_covers_libreoffice_only_and_none(tmp_path, monkeypatch):
    word_path = tmp_path / 'input.docx'
    pdf_path = tmp_path / 'output.pdf'
    word_path.write_bytes(b'word')

    monkeypatch.setattr(pdf_server, 'MS_OFFICE_AVAILABLE', False)
    monkeypatch.setattr(pdf_server, 'LIBREOFFICE_PATH', 'soffice')
    monkeypatch.setattr(pdf_server, 'convert_with_libreoffice', lambda _word, output_dir: ((Path(output_dir) / 'input.pdf').write_bytes(b'%PDF') or True, None))
    assert pdf_server._try_convert(str(word_path), str(pdf_path))[:2] == (True, 'LibreOffice')

    monkeypatch.setattr(pdf_server, 'LIBREOFFICE_PATH', None)
    assert pdf_server._try_convert(str(word_path), str(pdf_path)) == (False, None, 'No PDF converter available')


def test_placeholder_replacement_and_gate_cover_headers_and_footers(tmp_path):
    template = tmp_path / 'template.docx'
    output = tmp_path / 'output.docx'
    with zipfile.ZipFile(template, 'w') as archive:
        body = '<w:document><w:body><w:p><w:r><w:t>&lt;docNo&gt;</w:t></w:r></w:p></w:body></w:document>'
        header = '<w:hdr><w:p><w:r><w:t>&lt;performedDate&gt;</w:t></w:r></w:p></w:hdr>'
        footer = '<w:ftr><w:p><w:r><w:t>&lt;approvedDate&gt;</w:t></w:r></w:p></w:ftr>'
        archive.writestr('word/document.xml', body)
        archive.writestr('word/header1.xml', header)
        archive.writestr('word/footer1.xml', footer)

    pdf_server.replace_placeholders_in_file(template, output, {
        'docNo': 'PW-26-0001',
        'performedDate': '01 Sep 2026',
        'approvedDate': '02 Sep 2026',
    })

    assert pdf_server._unresolved_placeholders(output) == []
    with zipfile.ZipFile(output) as archive:
        assert 'PW-26-0001' in archive.read('word/document.xml').decode('utf-8')
        assert '01 Sep 2026' in archive.read('word/header1.xml').decode('utf-8')
        assert '02 Sep 2026' in archive.read('word/footer1.xml').decode('utf-8')


def test_textbox_placeholder_replacement_keeps_alternate_shapes_separate(tmp_path):
    template = Path(__file__).resolve().parents[2] / 'templates' / 'cv-contact-template.docx'
    output = tmp_path / 'cv-contact.docx'

    pdf_server.replace_placeholders_in_file(template, output, {
        'samplingDate': '01 Sep 2026',
        'samplingPoint04': '',
        'samplingPoint05': '',
        'samplingPoint06': '',
        'samplingPoint07': '',
    })

    with zipfile.ZipFile(output) as archive:
        document = archive.read('word/document.xml').decode('utf-8')
    assert document.count('01 Sep 2026') == 2
    assert '01 Sep 202601 Sep 2026' not in document
    for key in ('samplingPoint04', 'samplingPoint05', 'samplingPoint06', 'samplingPoint07'):
        assert key not in document


def test_pdf_cache_is_incomplete_without_the_controlled_docx(client):
    payload = {
        'workflow': 'pw-prw',
        'worksheetNo': 'PW-26-0002',
        'data': {'analyst': 'A'},
    }
    first = client.post('/api/pdfs', json=payload)
    assert first.status_code == 201
    created = first.get_json()
    word_path = Path(pdf_server.PROJECT_SHARE_ROOT) / 'words' / 'pw-prw' / 'PW-26-0002.docx'
    word_path.unlink()

    regenerated = client.post('/api/pdfs', json=payload)
    assert regenerated.status_code == 201
    assert regenerated.get_json()['cached'] is False
    assert word_path.is_file()


def test_pdf_cache_regenerates_stale_or_empty_artifacts(client):
    payload = {
        'workflow': 'pw-prw',
        'worksheetNo': 'PW-26-0003',
        'data': {'analyst': 'A'},
    }
    first = client.post('/api/pdfs', json=payload)
    assert first.status_code == 201
    pdf_id = first.get_json()['pdfId']
    pdf_path = Path(pdf_server.PROJECT_SHARE_ROOT) / 'pdfs' / 'pw-prw' / 'PW-26-0003.pdf'
    metadata_path = Path(pdf_server.PROJECT_SHARE_ROOT) / 'manifests' / 'pw-prw' / 'PW-26-0003' / 'PW-26-0003.json'
    word_path = Path(pdf_server.PROJECT_SHARE_ROOT) / 'words' / 'pw-prw' / 'PW-26-0003.docx'

    metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
    metadata['rendererVersion'] = 'old-renderer'
    Path(metadata_path).write_text(json.dumps(metadata), encoding='utf-8')
    Path(pdf_path).write_bytes(b'')
    word_path.write_bytes(b'')

    regenerated = client.post('/api/pdfs', json=payload)
    assert regenerated.status_code == 201
    assert regenerated.get_json()['cached'] is False
    assert Path(pdf_path).read_bytes().startswith(b'%PDF')
    assert zipfile.is_zipfile(word_path)
    refreshed = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
    assert refreshed['rendererVersion'] == pdf_server.DOCX_RENDERER_VERSION


def test_pdf_cache_regenerates_nonempty_invalid_pdf(client):
    payload = {
        'workflow': 'pw-prw',
        'worksheetNo': 'PW-26-0004',
        'data': {'analyst': 'A'},
    }
    first = client.post('/api/pdfs', json=payload)
    assert first.status_code == 201
    pdf_path = Path(pdf_server.PROJECT_SHARE_ROOT) / 'pdfs' / 'pw-prw' / 'PW-26-0004.pdf'
    Path(pdf_path).write_bytes(b'not a pdf')

    regenerated = client.post('/api/pdfs', json=payload)
    assert regenerated.status_code == 201
    assert regenerated.get_json()['cached'] is False
    assert Path(pdf_path).read_bytes().startswith(b'%PDF-')


def test_controlled_replacement_requires_exact_confirmed_conflict_set(client):
    initial = {
        'workflow': 'cleaning-validation-contact',
        'worksheetNo': 'CV-26-B10-0001',
        'data': {'sampleMatrix': 'Contact Plate', 'analyst': 'A'}
    }
    first = client.post('/api/pdfs', json=initial)
    assert first.status_code == 201

    changed = {**initial, 'data': {'sampleMatrix': 'Contact Plate', 'analyst': 'B'}}
    conflict = client.post('/api/pdfs', json=changed)
    assert conflict.status_code == 409
    body = conflict.get_json()
    assert body['code'] == 'WORKSHEET_CONTENT_CONFLICT'
    assert body['worksheetNo'] == 'CV-26-B10-0001'
    assert body['workflow'] == 'cleaning-validation-contact'
    assert body['existingPdfIds'] == [first.get_json()['pdfId']]
    assert body['changedFields'] == ['analyst']

    stale = client.post('/api/pdfs', json={**changed, 'regeneration': {
        'mode': 'replace', 'requestedPdfId': body['requestedPdfId'], 'existingPdfIds': []
    }})
    assert stale.status_code == 409

    replaced = client.post('/api/pdfs', json={**changed, 'regeneration': {
        'mode': 'replace', 'requestedPdfId': body['requestedPdfId'],
        'existingPdfIds': body['existingPdfIds']
    }})
    assert replaced.status_code == 201
    assert client.get(f"/api/pdfs/{first.get_json()['pdfId']}").status_code == 404
    metadata = client.get(f"/api/pdfs/{replaced.get_json()['pdfId']}").get_json()
    assert metadata['pdfId'] == replaced.get_json()['pdfId']


def test_failed_replacement_keeps_existing_artifacts_usable(client, monkeypatch):
    payload = {'workflow': 'cleaning-validation-rinse-membrane', 'worksheetNo': 'CVR-26-B16-0001',
               'cvContext': {'samplingFamily': 'Rinse', 'testMethod': 'Membrane Filtration'},
               'data': {'sampleMatrix': 'Rinse', 'analyst': 'A'}}
    first = client.post('/api/pdfs', json=payload)
    assert first.status_code == 201
    first_id = first.get_json()['pdfId']
    monkeypatch.setattr(pdf_server, 'convert_to_pdf', lambda *_args: (False, None, 'broken converter'))
    changed = {**payload, 'data': {'sampleMatrix': 'Rinse', 'analyst': 'B'}}
    conflict = client.post('/api/pdfs', json=changed).get_json()
    failed = client.post('/api/pdfs', json={**changed, 'regeneration': {
        'mode': 'replace', 'requestedPdfId': conflict['requestedPdfId'],
        'existingPdfIds': conflict['existingPdfIds']
    }})
    assert failed.status_code == 503
    assert client.get(f"/api/pdfs/{first_id}").status_code == 200


@pytest.mark.parametrize('fail_on', range(1, 9))
def test_artifact_promotion_rolls_back_every_mid_commit_failure(tmp_path, monkeypatch, fail_on):
    old_word = tmp_path / 'worksheet.docx'
    old_pdf = tmp_path / 'old.pdf'
    old_metadata = tmp_path / 'old.json'
    superseded_pdf = tmp_path / 'superseded.pdf'
    superseded_metadata = tmp_path / 'superseded.json'
    new_word = tmp_path / 'new.docx'
    new_pdf = tmp_path / 'new.pdf'
    new_metadata = tmp_path / 'new.json'
    old_word.write_bytes(b'old word')
    old_pdf.write_bytes(b'old pdf')
    old_metadata.write_bytes(b'old metadata')
    superseded_pdf.write_bytes(b'superseded pdf')
    superseded_metadata.write_bytes(b'superseded metadata')
    new_word.write_bytes(b'new word')
    new_pdf.write_bytes(b'new pdf')
    new_metadata.write_bytes(b'new metadata')
    real_replace = pdf_server.os.replace
    calls = {'count': 0}

    def fail_replace(source, destination):
        calls['count'] += 1
        if calls['count'] == fail_on:
            raise OSError('injected promotion failure')
        return real_replace(source, destination)

    monkeypatch.setattr(pdf_server.os, 'replace', fail_replace)
    with pytest.raises(OSError):
        pdf_server._replace_artifact_set(
            ((str(new_word), str(old_word)), (str(new_pdf), str(old_pdf)), (str(new_metadata), str(old_metadata))),
            (str(superseded_pdf), str(superseded_metadata))
        )
    assert old_word.read_bytes() == b'old word'
    assert old_pdf.read_bytes() == b'old pdf'
    assert old_metadata.read_bytes() == b'old metadata'
    assert superseded_pdf.read_bytes() == b'superseded pdf'
    assert superseded_metadata.read_bytes() == b'superseded metadata'
    assert not list(tmp_path.glob('*.rollback'))


def test_artifact_commit_keeps_new_set_when_backup_cleanup_fails(tmp_path, monkeypatch):
    old_word = tmp_path / 'worksheet.docx'
    old_word.write_bytes(b'old word')
    new_word = tmp_path / 'new.docx'
    new_pdf = tmp_path / 'new.pdf'
    new_metadata = tmp_path / 'new.json'
    superseded = tmp_path / 'superseded.pdf'
    new_word.write_bytes(b'new word')
    new_pdf.write_bytes(b'new pdf')
    new_metadata.write_bytes(b'new metadata')
    superseded.write_bytes(b'old superseded')

    real_remove = pdf_server.os.remove

    def fail_backup_cleanup(path):
        if path.endswith('.rollback'):
            raise OSError('injected cleanup failure')
        return real_remove(path)

    monkeypatch.setattr(pdf_server.os, 'remove', fail_backup_cleanup)
    pdf_server._replace_artifact_set(
        ((str(new_word), str(old_word)), (str(new_pdf), str(tmp_path / 'current.pdf')),
         (str(new_metadata), str(tmp_path / 'current.json'))),
        (str(superseded),)
    )

    assert old_word.read_bytes() == b'new word'
    assert (tmp_path / 'current.pdf').read_bytes() == b'new pdf'
    assert (tmp_path / 'current.json').read_bytes() == b'new metadata'
    assert not superseded.exists()
    assert not list(tmp_path.glob('*.rollback'))


def test_artifact_commit_keeps_primary_set_consistent_when_cleanup_is_unavailable(tmp_path, monkeypatch):
    old_word = tmp_path / 'worksheet.docx'
    old_word.write_bytes(b'old word')
    new_word = tmp_path / 'new.docx'
    new_pdf = tmp_path / 'new.pdf'
    new_metadata = tmp_path / 'new.json'
    superseded = tmp_path / 'superseded.pdf'
    new_word.write_bytes(b'new word')
    new_pdf.write_bytes(b'new pdf')
    new_metadata.write_bytes(b'new metadata')
    superseded.write_bytes(b'old superseded')

    real_remove = pdf_server.os.remove
    real_unlink = pdf_server.os.unlink

    def fail_remove(path):
        if path.endswith('.rollback'):
            raise OSError('injected remove failure')
        return real_remove(path)

    def fail_unlink(path):
        if path.endswith('.rollback'):
            raise OSError('injected unlink failure')
        return real_unlink(path)

    monkeypatch.setattr(pdf_server.os, 'remove', fail_remove)
    monkeypatch.setattr(pdf_server.os, 'unlink', fail_unlink)
    pdf_server._replace_artifact_set(
        ((str(new_word), str(old_word)), (str(new_pdf), str(tmp_path / 'current.pdf')),
         (str(new_metadata), str(tmp_path / 'current.json'))),
        (str(superseded),)
    )

    # An unavailable cleanup operation may leave isolated rollback evidence,
    # but it must never leave the user-facing document set half old/half new.
    assert old_word.read_bytes() == b'new word'
    assert (tmp_path / 'current.pdf').read_bytes() == b'new pdf'
    assert (tmp_path / 'current.json').read_bytes() == b'new metadata'
    rollback_paths = sorted(tmp_path.glob('*.rollback'))
    assert rollback_paths
    assert all(path.read_bytes() == b'old word' or path.read_bytes() == b'old superseded'
               for path in rollback_paths)


def test_real_multipage_template_is_valid_docx(tmp_path):
    output = tmp_path / 'em-multipage.docx'
    pdf_server.build_multipage_docx(
        str(Path(pdf_server.BASE_DIR) / 'templates' / 'em-template.docx'),
        str(output),
        [
            {'docNo': 'AT-26-QA-0001', 'building': 'QA', 'samplingDate': '01 Sep 2026'},
            {'docNo': 'AT-26-QA-0001', 'building': 'QA', 'samplingDate': '01 Sep 2026'},
        ],
    )

    with zipfile.ZipFile(output) as archive:
        document_xml = archive.read('word/document.xml')
    root = ET.fromstring(document_xml)
    assert len(root.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr')) >= 2
    assert document_xml.count(b'AT-26-QA-0001') >= 2


def test_compressed_air_multipage_vml_ids_are_unique(tmp_path):
    output = tmp_path / 'ca-multipage.docx'
    template = Path(pdf_server.BASE_DIR) / 'templates' / 'ca-template.docx'
    pdf_server.build_multipage_docx(
        str(template),
        str(output),
        [
            {'docNo': 'AC-26-B12-0001', 'building': 'B12', 'samplingDate': '01 Sep 2026'},
            {'docNo': 'AC-26-B12-0001', 'building': 'B12', 'samplingDate': '01 Sep 2026'},
        ],
    )

    with zipfile.ZipFile(output) as archive:
        document_xml = archive.read('word/document.xml').decode('utf-8')
    with zipfile.ZipFile(template) as archive:
        template_xml = archive.read('word/document.xml').decode('utf-8')

    page_break = '<w:p><w:pPr><w:sectPr><w:type w:val="nextPage"/>'
    pages = document_xml.split(page_break)
    assert len(pages) == 2
    page_one, page_two = pages

    vml_id_pattern = r'(?:(?:o:spid|id)="(_x0000_[sit]\d+(?:_p\d+)?)")'
    page_one_ids = re.findall(vml_id_pattern, page_one)
    page_two_ids = re.findall(vml_id_pattern, page_two)
    template_ids = re.findall(vml_id_pattern, template_xml)
    assert page_one_ids == template_ids
    assert page_one_ids
    assert all(not value.endswith(('_p1', '_p2')) for value in page_one_ids)
    assert page_two_ids
    assert all(value.endswith('_p2') for value in page_two_ids)
    assert set(page_one_ids).isdisjoint(page_two_ids)

    docpr_ids = re.findall(r'<wp:docPr\b[^>]*\bid="([0-9]+)"', document_xml)
    assert len(docpr_ids) == len(set(docpr_ids))

    page_two_types = set(re.findall(r'type="#(_x0000_t\d+_p2)"', page_two))
    page_two_shapetypes = set(re.findall(r'<v:shapetype[^>]+id="(_x0000_t\d+_p2)"', page_two))
    assert page_two_types
    assert page_two_types == page_two_shapetypes
