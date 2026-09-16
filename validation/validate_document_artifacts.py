"""Generate and inspect local synthetic DOCX/PDF pairs for every controlled route.

The input values are explicitly marked fixture values and the server is local;
this script never reads or writes Google Sheets or a deployed endpoint.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = os.environ.get("ANF3_ARTIFACT_SERVER", "http://127.0.0.1:8000")
ARTIFACT_DIR = ROOT / "output" / "document-artifacts"
ROUTES = [
    ("pw-prw", "PW-26-B10-9001", "pw-prw", None),
    ("wfi-pus", "WP-26-B16-9001", "wfi-pus", None),
    ("em-air", "AT-26-B10-9001", "em-air", None),
    ("compressed-air", "AC-26-B12-9001", "compressed-air", None),
    ("cleaning-validation-contact", "CV-26-B10-9001", "cleaning-validation-contact", {
        "samplingFamily": "Contact Plate", "testMethod": "Contact Plate"
    }),
    ("cleaning-validation-rinse-pour", "CVR-26-B16-9001", "cleaning-validation-rinse-pour", {
        "samplingFamily": "Rinse", "testMethod": "Pour Plate"
    }),
    ("cleaning-validation-rinse-membrane", "CVR-26-B16-9002", "cleaning-validation-rinse-membrane", {
        "samplingFamily": "Rinse", "testMethod": "Membrane Filtration"
    }),
]

# Keep fixture worksheet identities valid while allowing repeated local runs
# after a template or payload change. The server must continue to reject a
# different document under an existing worksheet identity; each validation
# run simply uses its own reserved numeric fixture suffix.
ARTIFACT_RUN = os.environ.get("ANF3_ARTIFACT_RUN", "9001").strip()
if not re.fullmatch(r"\d{4}", ARTIFACT_RUN):
    raise ValueError("ANF3_ARTIFACT_RUN must be exactly four digits")

EXPECTED_PAGES = {
    "pw-prw": 1,
    "wfi-pus": 1,
    "em-air": 2,
    "compressed-air": 2,
    "cleaning-validation-contact": 1,
    "cleaning-validation-rinse-pour": 2,
    "cleaning-validation-rinse-membrane": 2,
}

SAMPLE_PREFIXES = {
    "pw-prw": ("samplingPoint", "tagNo", "result1", "result2", "resultAvg"),
    "wfi-pus": ("samplingPoint", "tagNo", "result"),
    "em-air": ("roomNo", "grade", "tempRoom", "rhRoom", "timeIn", "timeOut", "occurResult", "remark"),
    "compressed-air": ("roomNo", "grade", "temp", "rh", "occResult", "remark"),
    "cleaning-validation-contact": ("samplingPoint", "Grade", "result"),
    "cleaning-validation-rinse-pour": ("tagNo", "samplingPoint", "result1", "result2", "resultAvg"),
    "cleaning-validation-rinse-membrane": ("tagNo", "samplingPoint", "result"),
}


def placeholder_names(template: Path) -> set[str]:
    names: set[str] = set()
    with zipfile.ZipFile(template) as archive:
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8")
            text = html.unescape("".join(re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", xml)))
            names.update(re.findall(r"<([A-Za-z][A-Za-z0-9 ]*)>", text))
    return names


def unresolved(path: Path) -> list[str]:
    names: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8")
            text = html.unescape("".join(re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", xml)))
            names.update(re.findall(r"<([A-Za-z][A-Za-z0-9 ]*)>", text))
    return sorted(names)


def docx_text(path: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8")
            chunks.extend(re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", xml))
    return html.unescape("".join(chunks))


def fixture_data(names: set[str], route: str, worksheet: str, page: int = 0) -> dict[str, str]:
    marker = f"QA-{route[:3].upper()}-P{page or 1}"
    data = {name: f"{marker}-FIELD-{index:02d}" for index, name in enumerate(sorted(names), 1)}
    data.update({
        "docNo": worksheet,
        "building": "QA fixture building",
        "samplingDate": "01 Sep 2026",
        "performedDate": "01 Sep 2026",
        "samplingPoint01": f"{marker}-PT01",
        "samplingTime": "QA-09:10",
        "sampleCount": str(51 if EXPECTED_PAGES[route] > 1 else 1),
    })
    if route == "cleaning-validation-contact":
        data["ProductName"] = "QA fixture product"
    return data


def page_fixture_data(names: set[str], route: str, worksheet: str, page: int) -> dict[str, str]:
    data = fixture_data(names, route, worksheet, page)
    for name in names:
        for prefix in SAMPLE_PREFIXES[route]:
            if re.fullmatch(re.escape(prefix) + r"\d{2}", name):
                data[name] = f"QA-{route[:3].upper()}-P{page}-S{name[-2:]}"
                break
    return data


def inspect_pdf(pdf_path: Path, stem: str, expected_pages: int, worksheet: str) -> dict:
    output = ARTIFACT_DIR / f"{stem}-page"
    info = subprocess.run(
        ["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )
    page_match = re.search(r"^Pages:\s+(\d+)", info.stdout, re.MULTILINE)
    pages = int(page_match.group(1)) if page_match else 0
    if pages < 1:
        raise RuntimeError(f"PDF has no pages: {pdf_path}")
    if pages < expected_pages:
        raise RuntimeError(f"expected at least {expected_pages} PDF pages, found {pages}")
    command = ["pdftoppm", "-f", "1", "-l", str(pages), "-png", str(pdf_path), str(output)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    except FileNotFoundError as error:
        raise RuntimeError("pdfinfo/pdftoppm is required for all-page artifact inspection") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"failed to render all {pages} PDF page(s): {error}") from error
    rendered = sorted(ARTIFACT_DIR.glob(f"{stem}-page-*.png"))
    if len(rendered) != pages:
        raise RuntimeError(f"expected {pages} rendered page images, found {len(rendered)}")
    text = subprocess.run(
        ["pdftotext", str(pdf_path), "-"], check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    ).stdout or ""
    if worksheet not in text:
        raise RuntimeError(f"PDF text does not contain worksheet identity {worksheet}")
    return {"pages": pages, "renderedPages": [str(path.relative_to(ROOT)) for path in rendered], "worksheetInText": True}


def request_json(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{SERVER}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    reports = []
    for route, worksheet_base, workflow, cv_context in ROUTES:
        worksheet = f"{worksheet_base[:-4]}{ARTIFACT_RUN}"
        template_name = {
            "pw-prw": "pw-prw-template.docx", "wfi-pus": "wfi-pus-template.docx",
            "em-air": "em-template.docx", "compressed-air": "ca-template.docx",
            "cleaning-validation-contact": "cv-contact-template.docx",
            "cleaning-validation-rinse-pour": "pw-prw-template.docx",
            "cleaning-validation-rinse-membrane": "wfi-pus-template.docx",
        }[route]
        names = placeholder_names(ROOT / "templates" / template_name)
        # Non-empty, route-local values prove that replacement happened without
        # using production records or inventing laboratory results.
        data = fixture_data(names, route, worksheet)
        payload = {"workflow": workflow, "worksheetNo": worksheet, "data": data}
        expected_pages = EXPECTED_PAGES[route]
        if expected_pages > 1:
            payload["pages"] = [page_fixture_data(names, route, worksheet, page) for page in range(1, expected_pages + 1)]
        if cv_context:
            payload["cvContext"] = cv_context
            data.update({"sampleMatrix": cv_context["samplingFamily"], "testMethod": cv_context["testMethod"]})

        response = request_json("/api/pdfs", payload)
        pdf_id = str(response["pdfId"])
        word_path = ROOT / "words" / workflow / f"{worksheet}.docx"
        pdf_path = ROOT / "pdfs" / workflow / f"{pdf_id}.pdf"
        if not word_path.is_file() or word_path.stat().st_size == 0:
            raise RuntimeError(f"{route}: missing generated DOCX {word_path}")
        if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            raise RuntimeError(f"{route}: missing generated PDF {pdf_path}")
        remaining = unresolved(word_path)
        if remaining:
            raise RuntimeError(f"{route}: unresolved placeholders {remaining}")
        word_text = docx_text(word_path)
        if "QA-" not in word_text:
            raise RuntimeError(f"{route}: DOCX contains no populated fixture value")
        preview = inspect_pdf(pdf_path, worksheet, expected_pages, worksheet)
        reports.append({
            "route": route, "worksheetNo": worksheet, "pdfId": pdf_id,
            "docx": str(word_path.relative_to(ROOT)), "pdf": str(pdf_path.relative_to(ROOT)),
            "docxBytes": word_path.stat().st_size, "pdfBytes": pdf_path.stat().st_size,
            "unresolvedPlaceholders": remaining, "preview": preview,
            "fixtureEvidence": {
                "nonEmptyValues": True, "route": route, "template": template_name,
                "expectedPages": expected_pages, "pagePayloadsSelfContained": expected_pages > 1,
                "worksheetInDocx": worksheet in word_text, "worksheetInPdf": preview["worksheetInText"],
            },
        })
        print(f"PASS {route}: {worksheet}.docx + {worksheet}.pdf route/template/placeholder checks")

    (ARTIFACT_DIR / "manifest.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(f"PASS seven synthetic route artifacts; manifest={ARTIFACT_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL document artifacts: {error}", file=sys.stderr)
        raise
