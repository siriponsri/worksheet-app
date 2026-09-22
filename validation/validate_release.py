from __future__ import annotations

from html.parser import HTMLParser
import argparse
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.styles: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")
        if tag == "link" and values.get("href"):
            self.styles.append(values["href"] or "")


def strip_suffix(value: str) -> str:
    return value.split("?", 1)[0].split("#", 1)[0]


def controlled_root() -> Path | None:
    parser = argparse.ArgumentParser(description="Validate the public source or a controlled ANF3 release package")
    parser.add_argument(
        "--controlled-dir",
        type=Path,
        help="external release directory containing owner-only documents and DOCX templates",
    )
    args = parser.parse_args()
    if args.controlled_dir is None:
        return None
    candidate = args.controlled_dir.expanduser().resolve()
    assert candidate.is_dir(), f"Controlled release directory does not exist: {candidate}"
    return candidate


def resolve_local_asset(html_file: Path, value: str) -> Path:
    """Resolve browser-style asset paths for source pages and the Vite app."""
    if value.startswith("/"):
        if "apps" in html_file.parts and "web" in html_file.parts:
            public_target = html_file.parent / "public" / value.lstrip("/")
            if public_target.exists():
                return public_target.resolve()
            return (html_file.parent / value.lstrip("/")).resolve()
        return (ROOT / value.lstrip("/")).resolve()
    return (html_file.parent / value).resolve()


def assert_local_assets() -> None:
    failures: list[str] = []
    html_files = [ROOT / "apps" / "web" / "index.html"]
    for html_file in html_files:
        assert html_file.is_file(), f"Missing active app shell: {html_file.relative_to(ROOT)}"
        parser = LinkParser()
        parser.feed(html_file.read_text(encoding="utf-8"))
        for value in parser.links + parser.scripts + parser.styles:
            value = strip_suffix(value)
            if not value or value.startswith(("http://", "https://", "mailto:", "javascript:", "#")):
                continue
            target = resolve_local_asset(html_file, value)
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                failures.append(f"{html_file.relative_to(ROOT)} -> outside root: {value}")
                continue
            if not target.exists():
                failures.append(f"{html_file.relative_to(ROOT)} -> missing: {value}")
    assert not failures, "Broken local assets:\n" + "\n".join(failures)


def assert_required_files(controlled: Path | None) -> None:
    required = [
        "START-ANF3.bat",
        "START-SERVER.bat",
        ".env.production",
        "apps/web/src/App.tsx",
        "apps/web/src/DeskScene.tsx",
        "apps/web/src/theme.ts",
        "apps/web/src/tokens.css",
        "apps/web/src/api.ts",
        "apps/web/src/storage.ts",
        "apps/web/src/recordPolicy.ts",
        "apps/web/src/styles.css",
        "apps/web/public/favicon.svg",
        "apps/web/public/catalog/inventory-index.json",
        "inventory_catalog.pdf",
        "google/app-scripts/air-test.gs",
        "google/app-scripts/RPP2-air-record.gs",
        "google/app-scripts/water-r.gs",
        "google/app-scripts/RPP2-water-record.gs",
        "google/app-scripts/Testing.gs",
        "google/app-scripts/RPP2-cv-record.gs",
    ]
    missing = [value for value in required if not (ROOT / value).is_file()]
    assert not missing, f"Missing required files: {missing}"

    if controlled is None:
        return

    controlled_required = [
        "inventory_catalog.pdf",
        "dist/index.html",
        "VERSION.txt",
        "config.json",
        "templates/pw-prw-template.docx",
        "templates/wfi-pus-template.docx",
        "templates/ca-template.docx",
        "templates/em-template.docx",
        "templates/cv-contact-template.docx",
    ]
    controlled_missing = [value for value in controlled_required if not (controlled / value).is_file()]
    assert not controlled_missing, f"Controlled release is missing required files: {controlled_missing}"


def assert_templates(controlled: Path | None) -> None:
    if controlled is None:
        print("Public source mode: controlled DOCX template checks skipped; use --controlled-dir for the share package")
        return
    for template in (controlled / "templates").glob("*.docx"):
        assert zipfile.is_zipfile(template), f"Invalid DOCX container: {template.name}"
        with zipfile.ZipFile(template) as archive:
            assert "word/document.xml" in archive.namelist(), f"document.xml missing: {template.name}"

    config = controlled / "config.json"
    try:
        parsed = json.loads(config.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AssertionError(f"Controlled config.json is invalid JSON: {error}") from error
    for key in ("waterReadUrl", "airReadUrl", "cvReadUrl"):
        value = str(parsed.get(key) or "").strip()
        assert not value or re.fullmatch(
            r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec", value
        ), f"Controlled config.json {key} must be blank or a public /exec URL"
        assert "ANF3_SYNC_TOKEN" not in value and "token" not in value.lower(), \
            f"Controlled config.json {key} contains a forbidden token"


def assert_navigation() -> None:
    app = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")
    data = (ROOT / "apps/web/src/appData.ts").read_text(encoding="utf-8")
    expected = [
        "records/:domain", "records/:domain/:workflow", "calendar", "inventory",
        "games/growth-promotion", "games/feller", "Cleaning Validation",
        "Coming Soon", "Stock DB", "Stock Web", "Document booking", "Upload Picture",
        "COA App", "http://192.168.1.10:8000"
    ]
    for value in expected:
        assert value in app + data, f"Navigation value missing: {value}"
    assert "createHashRouter" in app
    assert "CalendarEmbed" in app


def assert_design_gates() -> None:
    """Design gates for the v7.1 rebuild.

    The scene is a fixed-camera shelf above a bench (DeskScene), not the old
    orbiting foyer, so the camera gate is now "no free orbit or zoom" rather
    than "OrbitControls configured". Every colour and font must resolve
    through a token in tokens.css.
    """
    styles = (ROOT / "apps/web/src/styles.css").read_text(encoding="utf-8")
    tokens = (ROOT / "apps/web/src/tokens.css").read_text(encoding="utf-8")
    desk = (ROOT / "apps/web/src/DeskScene.tsx").read_text(encoding="utf-8")
    app = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")

    # The blanket gradient ban was aimed at the purple-hero tell: gradient
    # text, gradient buttons, multi-hue decorative washes. A single-token
    # surface wash — the paper beside a binder spine — is not that, so the
    # gate now names what it actually protects against.
    assert "background-clip: text" not in styles, "no gradient text"
    assert "-webkit-background-clip: text" not in styles, "no gradient text"
    # Only COLOUR tokens count. The rule protects against multi-hue decorative
    # washes, and it said so in its own variable name -- but it counted every
    # var(), so a gradient that takes its colour from one token and its
    # spacing from another (the calibration ticks along a panel edge) tripped
    # it. A length is not a hue. Resolved from tokens.css rather than guessed:
    # a token whose value is an oklch() is a colour, anything else is not.
    colour_tokens = {
        name for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", tokens)
        if "oklch(" in value
    }
    # Parentheses are matched, not guessed. The previous pattern stopped at
    # the first ")", which inside `linear-gradient(90deg, var(--a), var(--b))`
    # is the one closing var(--a) -- so the plainest two-colour gradient, the
    # exact thing this gate exists to stop, sailed straight through it while a
    # more nested one was caught. Proven by adding one and watching it pass.
    for match in re.finditer(r"(?:repeating-)?(?:linear|radial|conic)-gradient\(", styles):
        depth, index = 0, match.end() - 1
        while index < len(styles):
            if styles[index] == "(":
                depth += 1
            elif styles[index] == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        gradient = styles[match.end():index]
        hues = {name for name in re.findall(r"var\((--[a-z0-9-]+)\)", gradient) if name in colour_tokens}
        assert len(hues) <= 1, f"a gradient may carry one colour token, not {sorted(hues)}"
    assert "gradient" not in re.sub(r"(?s)/\*.*?\*/", "", styles).split(".actions")[-1][:600], \
        "no gradient fills on buttons"
    assert "focus-visible" in styles
    assert "prefers-reduced-motion" in styles
    assert "overflow-x: clip" in styles, "root must clip, never hide"
    assert "OrbitControls" not in desk, "the camera is fixed; no free orbit"
    assert "readRoomPalette" in desk and "resolveToken" in desk, "3D colours come from tokens"

    for token in ("--b10-spine", "--b12-spine", "--b16-spine", "--other-spine", "--reserve-spine",
                  "--color-accent", "--font-display", "--font-body", "--font-data", "--space-md"):
        assert token in tokens, f"design token missing: {token}"

    # v7.1 workbench: a building tab strip over the shelf, a dense binder list
    # beside it, and a status line — no accordion, no hero, no page scroll.
    assert "shelf-tabs" in app and "binder-row" in app and "workbench" in app
    assert "role=\"tablist\"" in app, "the building selector is a real tab strip"
    assert "requestOpen" in app, "opening a binder plays before the route changes"
    assert "Coming Soon" in app + (ROOT / "apps/web/src/appData.ts").read_text(encoding="utf-8")
    assert "H2O" not in app + desk and "O2" not in app + desk
    assert "@media (max-width: 60rem)" in styles, "rail must collapse on narrow viewports"
    assert "100dvh" in styles, "the workbench fills the viewport"


def assert_cv_boundaries() -> None:
    app = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")
    policy = (ROOT / "apps/web/src/recordPolicy.ts").read_text(encoding="utf-8")
    server = (ROOT / "server/pdf_server.py").read_text(encoding="utf-8")
    cv_user = (ROOT / "google/app-scripts/Testing.gs").read_text(encoding="utf-8")
    cv_system = (ROOT / "google/app-scripts/RPP2-cv-record.gs").read_text(encoding="utf-8")
    assert "SOURCE_SHEET: 'CV'" in cv_user
    assert "domain: 'cv'" in cv_user
    assert "TARGET_ID: '1g6klceQWA4Duy5Eq2Az0LE47-2WUUXZE2fAPFBSKHrE'" in cv_system
    assert "This endpoint accepts domain=cv only" in cv_system
    assert "generateCvWorksheetNo_" in cv_system
    assert "CONTACT_SHEETS" in cv_system
    assert "records_cv_contact_B10" in cv_system and "records_cv_contact_OT" in cv_system
    assert "RINSE_SHEETS" in cv_system
    assert "record_cv_rinse_B10" in cv_system and "record_cv_rinse_OT" in cv_system
    assert "records_cv_samples" not in cv_system
    assert re.search(r"recordId.*worksheetNo.*domain", cv_system, re.S)
    assert "cv-method" in policy
    assert "cleaning-validation-rinse-pour" in app + policy
    assert "cleaning-validation-rinse-membrane" in app + policy
    assert "_validate_pdf_route" in server


def assert_endpoint_configuration() -> None:
    env_text = (ROOT / ".env.production").read_text(encoding="utf-8")
    assert "VITE_AIR_READ_URL=https://script.google.com/macros/s/" in env_text
    assert "VITE_WATER_READ_URL=https://script.google.com/macros/s/" in env_text
    assert "VITE_CV_READ_URL=" in env_text
    assert "ANF3_SYNC_TOKEN" not in env_text


def assert_launcher_repairs_venv() -> None:
    """A .venv that was copied, moved or half-restored still contains
    python.exe but no usable pyvenv.cfg. Checking only for python.exe let the
    launcher start it anyway, and the owner got a bare "No pyvenv.cfg file"
    with no way forward. Both scripts must probe pyvenv.cfg and rebuild."""
    for name in ("INSTALL.bat", "START-SERVER.bat"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "pyvenv.cfg" in text, f"{name} does not check pyvenv.cfg"
    install = (ROOT / "INSTALL.bat").read_text(encoding="utf-8")
    assert "rmdir /s /q" in install, "INSTALL.bat cannot rebuild a broken .venv"
    start = (ROOT / "START-SERVER.bat").read_text(encoding="utf-8")
    assert "import flask" in start, "START-SERVER.bat does not verify the dependency"
    assert "call \"%APP_DIR%INSTALL.bat\"" in start, "START-SERVER.bat does not self-repair"


def main() -> None:
    controlled = controlled_root()
    assert_required_files(controlled)
    assert_local_assets()
    assert_templates(controlled)
    assert_navigation()
    assert_design_gates()
    assert_cv_boundaries()
    assert_endpoint_configuration()
    assert_launcher_repairs_venv()
    mode = "controlled release" if controlled else "public source"
    print(f"{mode.capitalize()} structural checks passed")


if __name__ == "__main__":
    main()
