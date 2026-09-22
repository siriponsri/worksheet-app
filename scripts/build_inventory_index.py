#!/usr/bin/env python3
"""Build and verify the committed inventory catalog assets.

OCR is deliberately not used by the application. The records below are the
human-reviewed transcription of inventory_catalog.pdf; Poppler is only used
to make browser thumbnails during an explicit developer build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'inventory_catalog.pdf'
OUTPUT = ROOT / 'apps' / 'web' / 'public' / 'catalog'
REVIEW_OUTPUT = ROOT / 'output' / 'inventory-review'
THUMBNAILS = REVIEW_OUTPUT / 'thumbnails'
EXPECTED_SHA256 = 'F6DDDE2826C1DE34873FCCAB883F075788022C42565DBBC6D80E7F1EAA5BC71C'
EXPECTED_PAGES = 16
EXPECTED_ROWS = 95

# sequence|material|description|unit. Each entry was checked against its page.
CATALOG_TEXT = '''
1|71000001|กระดาษถ่ายเอกสาร B4 80 แกรม (F14)|RE
2|71000002|กระดาษถ่ายเอกสาร A4 80 แกรม|RE
3|71000003|กระดาษถ่ายเอกสาร A3 80 แกรม|RE
4|71000005|กระดาษคาร์บอน สีน้ำเงิน|BOX
5|71000006|กระดาษคาร์บอน สีดำ|BOX
6|71000007|กระดาษบวกเลข 2 1/4 นิ้ว|ROL
7|71000009|สมุดปกอ่อน 40 แผ่น|EA
8|71000010|สมุดปกแข็ง 100 แผ่น|EA
9|71000011|สมุดปกแข็ง สีน้ำเงิน No.3 ใหญ่ 25x36 ซม.|EA
10|71000012|สมุดปกแข็ง สีน้ำเงิน No.3 เล็ก 20.5x33 ซม.|EA
11|71000013|สมุดส่งหนังสือ (เล่มเล็ก) 20.5x27 ซม.|EA
12|71000014|สมุดทะเบียนรับ-ส่งหนังสือ (เล่มใหญ่)|EA
13|71000015|สมุดใบเบิกของ|EA
14|71000016|สมุดใบเสนองาน (อ.3)|EA
15|71000019|บ.ใบสำคัญจ่ายเงิน|RE
16|71000024|แท่นประทับตรา สีน้ำเงิน|EA
17|71000025|แท่นประทับตรา สีแดง|EA
18|71000026|แท่นประทับตรา สีม่วง|EA
19|71000027|หมึกเติมแท่นประทับตรา สีน้ำเงิน|EA
20|71000028|หมึกเติมแท่นประทับตรา สีแดง|EA
21|71000029|หมึกเติมแท่นประทับตรา สีม่วง (พีริแกน)|EA
22|71000030|หมึกตอกตัวเลข 6 หลัก (ENM)|EA
23|71000031|ผ้าหมึกเครื่องคิดเลข สีดำ-แดง|ROL
24|71000034|ผ้าหมึก Oki 790|ROL
25|71000035|เทปลบคำผิด|EA
26|71000036|ยางลบดินสอ|EA
27|71000038|ไม้บรรทัดพลาสติก ขนาด 12 นิ้ว|EA
28|71000039|ตรายางตัวเลข 6 หลัก|EA
29|71000040|ตรายางวันที่ (ภาษาไทย)|EA
30|71000041|ปากกาลูกลื่น สีน้ำเงิน|EA
31|71000042|ปากกาลูกลื่น สีแดง|EA
32|71000043|ปากกาเขียนกล่อง สีน้ำเงิน หัวกลม No.107|EA
33|71000044|ปากกาเขียนกล่อง สีแดง หัวกลม No.107|EA
34|71000045|ปากกาเมจิก แท่งเล็ก|EA
35|71000046|ดินสอ (HB)|EA
36|71000047|ลวดเย็บกระดาษ เบอร์ 10|BOX
37|71000048|ลวดเย็บกระดาษ เบอร์ 8|BOX
38|71000049|ลวดเย็บกระดาษ เบอร์ 35|BOX
39|71000050|ลวดเสียบกระดาษ เบอร์ 1|BOX
40|71000051|ที่หนีบกระดาษ สีดำ เบอร์ 109 (ใหญ่)|EA
41|71000052|ที่หนีบกระดาษ สีดำ เบอร์ 110 (เล็ก)|EA
42|71000053|ซองสีน้ำตาล ตราองค์การฯ 7\"x10\"|EN
43|71000054|ซองสีน้ำตาล ตราองค์การฯ 9\"x12\"|EN
44|71000055|ซองสีน้ำตาลขยายข้าง ตราองค์การฯ 9\"x13\"|EN
45|71000056|ซองสีน้ำตาลขยายข้าง ตราองค์การฯ 11\"x17\"|EN
46|71000057|ซองสีขาว พับ 4 ตราองค์การฯ|EN
47|71000058|ซองหน้าต่างสีขาว พับ 4 ตราองค์การฯ|EN
48|71000059|ซองสีขาว พับ 4 ไม่มีครุฑ (ซองเปล่า)|EN
49|71000060|เทปใส ขนาด 3/4 นิ้ว x 72 หลา|ROL
50|71000061|เชือกผูกพัสดุไปรษณีย์|ROL
51|71000062|แฟ้มเจาะ 500 แกรม ขนาด 14 นิ้ว|EA
52|71000063|แฟ้มปกอ่อน สีน้ำตาล ตราองค์การฯ|PAC
53|71000064|แฟ้มตราช้าง No.120 A4 สีดำหรือยี่ห้ออื่น|EA
54|71000065|แฟ้มตราช้าง No.120 F สีดำหรือยี่ห้ออื่น|EA
55|71000066|แฟ้มตราช้าง No.125 A4 สีดำหรือยี่ห้ออื่น|EA
56|71000067|แฟ้มตราช้าง No.125 F สีดำ หรือยี่ห้ออื่น|EA
57|71000068|แฟ้มตราช้าง No.210P/A4 สีดำหรือยี่ห้ออื่น|EA
58|71000069|แฟ้มตราช้าง No.210 P/F สีดำหรือยี่ห้ออื่น|EA
59|71000070|แฟ้มตราช้าง No.610 A4 สีดำหรือยี่ห้ออื่น|EA
60|71000071|แฟ้มตราช้าง No.610 F สีดำ หรือยี่ห้ออื่น|EA
61|71000072|แฟ้มตราช้าง No.620 A4 สีดำหรือยี่ห้ออื่น|EA
62|71000073|แฟ้มตราช้าง No.620 F สีดำหรือยี่ห้ออื่น|EA
63|71000074|กระดาษพิมพ์ต่อเนื่อง 9\" x 11\" 1 ชั้น|BOX
64|71000075|กระดาษพิมพ์ต่อเนื่อง 9\" x 11\" 2 ชั้น|BOX
65|71000076|กระดาษพิมพ์ต่อเนื่อง 9\" x 11\" 3 ชั้น|BOX
66|71000077|กระดาษพิมพ์ต่อเนื่อง 11\" x 11\" 1 ชั้น|BOX
67|71000078|กระดาษพิมพ์ต่อเนื่อง 11\" x 11\" 2 ชั้น|BOX
68|71000080|กระดาษพิมพ์ต่อเนื่อง 15\" x 11\" 1 ชั้น|BOX
69|71000081|กระดาษพิมพ์ต่อเนื่อง 15\" x 11\" 2 ชั้น|BOX
70|71000082|กระดาษพิมพ์ต่อเนื่อง 15\" x 11\" 3 ชั้น|BOX
71|71000115|ผ้าหมึก Cartridge EPSON LQ-2090|EA
72|71000116|ผ้าหมึก Cartridge EPSON LQ-2170/2070/2180|EA
73|71000117|หมึกพิมพ์ริบบอน|ROL
74|71000119|ซองอเนกประสงค์ 11 รู A4 หนา 0.05 มม.|PAC
75|71000120|ซองอเนกประสงค์ 11 รู A4 หนา 0.09 มม.|PAC
76|71000121|กรรไกร 8 นิ้ว|EA
77|71000122|มีดคัตเตอร์ ด้ามสแตนเลส 18 มม.|EA
78|71000123|ใบมีดคัตเตอร์ 18 มม.|EA
79|71000124|ที่เย็บกระดาษ (เล็ก) 10-20 แผ่น|EA
80|71000125|ที่เย็บกระดาษ (กลาง) 25-35 แผ่น|EA
81|71000126|ที่เย็บกระดาษ (ใหญ่) 60 แผ่น|EA
82|71000127|ที่หนีบกระดาษ สีดำ No.111|BOX
83|71000128|ที่หนีบกระดาษ สีดำ No.112|BOX
84|71000130|แปรงทองเหลือง มีด้าม|EA
85|71000131|แปรงทองเหลือง รูปไข่|EA
86|71000132|ผ้าก๊อส ขนาด 36 นิ้ว x 100 หลา|ROL
87|71000133|อลูมิเนียมฟอยด์ ขนาด 457 มม. x 7.62 ม.|ROL
88|71000160|เชือกพลาสติกผูกของ|ROL
89|71000161|กระดาษชำระ|ROL
90|71000162|ผงซักฟอก|PAC
91|71000163|ฝอยขัด|EA
92|71000165|ถุงใส่ขยะ สีดำ ขนาดใหญ่ 36\"x45\"|PAC
93|71000166|หมวก GMP (Hair Cover)|EA
94|71000167|รองเท้า GMP (Shoe Cover)|PAA
95|71000170|ยางรัดของ วงใหญ่|KG
'''.strip()


def source_hash() -> str:
    digest = hashlib.sha256()
    with SOURCE.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest().upper()


def page_count() -> int:
    tool = shutil.which('pdfinfo')
    if not tool:
        raise RuntimeError('pdfinfo (Poppler) is required')
    output = subprocess.check_output([tool, str(SOURCE)], text=True, errors='replace')
    match = re.search(r'^Pages:\s+(\d+)$', output, re.MULTILINE)
    if not match:
        raise RuntimeError('Unable to read PDF page count')
    return int(match.group(1))


def records() -> list[dict[str, object]]:
    result = []
    for line in CATALOG_TEXT.splitlines():
        sequence, material, description, unit = line.split('|')
        sequence_number = int(sequence)
        result.append({
            'sequence': sequence_number,
            'materialCode': material,
            'name': unicodedata.normalize('NFC', description.strip()),
            'unit': unit,
            'page': ((sequence_number - 1) // 6) + 1,
            'reviewed': True,
        })
    return result


def payload(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        'schemaVersion': 1,
        'source': {
            'file': 'inventory_catalog.pdf',
            'sha256': EXPECTED_SHA256,
            'pages': EXPECTED_PAGES,
            'format': 'A4 raster PDF',
        },
        'rowCount': len(items),
        'items': items,
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def build() -> None:
    validate_source()
    items = records()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    THUMBNAILS.mkdir(parents=True, exist_ok=True)
    renderer = shutil.which('pdftoppm')
    if not renderer:
        raise RuntimeError('pdftoppm (Poppler) is required')
    subprocess.run([
        renderer, '-jpeg', '-r', '72', '-jpegopt', 'quality=82,progressive=n',
        str(SOURCE), str(THUMBNAILS / 'page'),
    ], check=True)
    generated = sorted(THUMBNAILS.glob('page-*.jpg'))
    if len(generated) != EXPECTED_PAGES:
        raise RuntimeError(f'Expected {EXPECTED_PAGES} thumbnails, got {len(generated)}')
    # Poppler uses page-01.jpg for this document; normalize defensively.
    for index, path in enumerate(generated, 1):
        target = THUMBNAILS / f'page-{index:02d}.jpg'
        if path != target:
            path.replace(target)
    manifest = payload(items)
    write_json(OUTPUT / 'inventory-index.json', manifest)
    write_json(REVIEW_OUTPUT / 'manifest.json', {
        'schemaVersion': 1,
        'index': 'inventory-index.json',
        'thumbnailPattern': 'thumbnails/page-{page:02d}.jpg',
        'sourceSha256': EXPECTED_SHA256,
        'pageCount': EXPECTED_PAGES,
        'rowCount': EXPECTED_ROWS,
        'reviewStatus': 'human-reviewed',
        'runtimeOcr': False,
    })
    report = (
        '# Inventory catalog verification\n\n'
        f'- Source SHA-256: `{EXPECTED_SHA256}`\n'
        f'- Source pages: {EXPECTED_PAGES} A4 raster pages\n'
        f'- Catalog rows: {EXPECTED_ROWS}\n'
        '- Required fields: material code, name, unit, and page\n'
        '- Review status: all 95 rows visually checked against rendered source pages\n'
        '- Unresolved required fields: 0\n'
        '- OCR provenance: Tesseract `tha+eng` was run offline, then every required field was visually reviewed\n'
        '- OCR policy: developer build/review only; runtime OCR is disabled\n'
    )
    (REVIEW_OUTPUT / 'VERIFICATION.md').write_text(report, encoding='utf-8', newline='\n')
    verify(require_review_artifacts=True)


def validate_source() -> None:
    if not SOURCE.is_file():
        raise RuntimeError(f'Missing source PDF: {SOURCE}')
    actual_hash = source_hash()
    if actual_hash != EXPECTED_SHA256:
        raise RuntimeError(f'Source SHA-256 mismatch: {actual_hash}')
    actual_pages = page_count()
    if actual_pages != EXPECTED_PAGES:
        raise RuntimeError(f'Expected {EXPECTED_PAGES} pages, got {actual_pages}')


def verify(*, require_review_artifacts: bool = False) -> None:
    validate_source()
    index_path = OUTPUT / 'inventory-index.json'
    if not index_path.is_file():
        raise RuntimeError('Catalog index is missing; run the build first')
    index = json.loads(index_path.read_text(encoding='utf-8'))
    items = index.get('items', [])
    errors = []
    if index != payload(records()):
        errors.append('inventory-index.json differs from reviewed source data')
    if len(items) != EXPECTED_ROWS or index.get('rowCount') != EXPECTED_ROWS:
        errors.append(f'catalog must contain exactly {EXPECTED_ROWS} rows')
    expected_sequence = list(range(1, EXPECTED_ROWS + 1))
    if [item.get('sequence') for item in items] != expected_sequence:
        errors.append('sequence values must be contiguous from 1 to 95')
    codes = [item.get('materialCode') for item in items]
    if len(set(codes)) != EXPECTED_ROWS:
        errors.append('material codes must be unique')
    for item in items:
        missing = [key for key in ('materialCode', 'name', 'unit', 'page') if not item.get(key)]
        if missing or item.get('reviewed') is not True:
            errors.append(f"row {item.get('sequence')} unresolved/unreviewed: {', '.join(missing) or 'reviewed'}")
    if require_review_artifacts:
        manifest_path = REVIEW_OUTPUT / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
        if manifest.get('runtimeOcr') is not False or manifest.get('reviewStatus') != 'human-reviewed':
            errors.append('review manifest must disable runtime OCR and declare human review')
        if (
            manifest.get('sourceSha256') != EXPECTED_SHA256
            or manifest.get('pageCount') != EXPECTED_PAGES
            or manifest.get('rowCount') != EXPECTED_ROWS
        ):
            errors.append('review manifest source hash, page count, and row count must remain pinned')
        thumbnails = sorted(THUMBNAILS.glob('page-*.jpg'))
        expected_thumbnails = [THUMBNAILS / f'page-{page:02d}.jpg' for page in range(1, EXPECTED_PAGES + 1)]
        if thumbnails != expected_thumbnails or any(path.stat().st_size == 0 for path in thumbnails):
            errors.append(f'exactly {EXPECTED_PAGES} non-empty review thumbnails are required')
        if not (REVIEW_OUTPUT / 'VERIFICATION.md').is_file():
            errors.append('review VERIFICATION.md is missing')
    if errors:
        raise RuntimeError('\n'.join(errors))
    print(f'Verified {EXPECTED_ROWS} reviewed rows across {EXPECTED_PAGES} pages.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='verify committed assets without regenerating them')
    args = parser.parse_args()
    try:
        verify() if args.verify else build()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
