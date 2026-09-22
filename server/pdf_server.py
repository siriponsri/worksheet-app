"""
============================================
PDF Server - Water Record System
============================================
Local server สำหรับสร้าง Word และแปลง PDF
ต้องติดตั้ง: pip install flask flask-cors pywin32
รองรับ: Microsoft Office (แนะนำ) หรือ LibreOffice
Version: 4.2.0 - Multi-folder support + Static Files
============================================
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, redirect, Response
import subprocess  # nosec - Used for controlled LibreOffice conversion
import sys
import os
import shutil
import json
import re
import zipfile
import tempfile
import hashlib
import socket
import threading
import uuid
from contextlib import contextmanager

from datetime import datetime

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore

import activity_log
from pathlib import Path

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

# ============================================
# Configuration
# ============================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, 'dist')
INVENTORY_PDF = os.path.join(BASE_DIR, 'inventory_catalog.pdf')
INVENTORY_INDEX_HASH = 'F6DDDE2826C1DE34873FCCAB883F075788022C42565DBBC6D80E7F1EAA5BC71C'
INVENTORY_INDEX_PATHS = (
    os.path.join(DIST_DIR, 'catalog', 'inventory-index.json'),
    os.path.join(BASE_DIR, 'apps', 'web', 'public', 'catalog', 'inventory-index.json')
)
# These folders are retained for compatibility with retired path-based APIs
# and tests. The supported document API writes controlled artifacts to the
# project share and uses the OS temp directory only while converting.
CACHE_ROOT = os.environ.get(
    'ANF3_CACHE_DIR', os.path.join(tempfile.gettempdir(), 'ANF3-Laboratory-Records-cache')
).strip()
WORDS_DIR = os.path.join(CACHE_ROOT, 'words')
PDFS_DIR = os.path.join(CACHE_ROOT, 'pdfs')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
# The share is server-only runtime configuration. The browser never receives
# this path and never writes to it directly.
PROJECT_SHARE_ROOT = os.environ.get('ANF3_PROJECT_SHARE', '').strip()
BACKUP_SPOOL_DIR = os.environ.get(
    'ANF3_BACKUP_SPOOL', os.path.join(BASE_DIR, 'backup-pending')
).strip()

PDF_WORKFLOW_REGISTRY = {
    'pw-prw': {
        'template': 'pw-prw-template.docx',
        'owner': 'water',
        'family': 'water-pw-prw'
    },
    'wfi-pus': {
        'template': 'wfi-pus-template.docx',
        'owner': 'water',
        'family': 'water-wfi-pus'
    },
    'compressed-air': {
        'template': 'ca-template.docx',
        'owner': 'air',
        'family': 'air-compressed'
    },
    'em-air': {
        'template': 'em-template.docx',
        'owner': 'air',
        'family': 'air-environmental'
    },
    # The owner approved the existing Water document families for CV Rinse.
    # They remain separate CV routes/adapters so a CV request cannot become a
    # Water request by submitting a filename.
    'cleaning-validation-contact': {
        'template': 'cv-contact-template.docx',
        'owner': 'cv',
        'family': 'cv-contact'
    },
    'cleaning-validation-rinse-pour': {
        'template': 'pw-prw-template.docx',
        'owner': 'cv',
        'family': 'cv-rinse-pour',
        'sourceWorkflow': 'pw-prw',
        'testMethod': 'pour-plate'
    },
    'cleaning-validation-rinse-membrane': {
        'template': 'wfi-pus-template.docx',
        'owner': 'cv',
        'family': 'cv-rinse-membrane',
        'sourceWorkflow': 'wfi-pus',
        'testMethod': 'membrane-filtration'
    }
}
WORKFLOW_TEMPLATES = {key: value['template'] for key, value in PDF_WORKFLOW_REGISTRY.items()}
LEGACY_PAGE_FOLDERS = ('pw-prw', 'wfi-pus', 'compressed-air', 'em-air', 'cv')
PDF_ID_RE = re.compile(r'^[0-9a-f]{64}$')
SAFE_KEY_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._ -]{0,119}$')
WINDOWS_DEVICE_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{number}' for number in range(1, 10)),
    *(f'LPT{number}' for number in range(1, 10))
}
CONVERSION_LOCK = threading.Lock()
DOCUMENT_GENERATION_LOCK = threading.Lock()
TEMPLATE_HASH_CACHE = {}
DOCX_RENDERER_VERSION = '2026-09-11-r1'
BACKUP_LOCK = threading.Lock()

# Form type folders
FORM_FOLDERS = [
    'pw-prw',
    'wfi-pus',
    'compressed-air',
    'em-air',
    'cleaning-validation',
    'cleaning-validation-contact',
    'cleaning-validation-rinse-pour',
    'cleaning-validation-rinse-membrane',
    'growth-promotion',
    'identification'
]

# Create folder structure
def create_folder_structure():
    """Create all necessary folders for the application"""
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    print("[OK] Folder structure created")

# Initialize folders on startup
create_folder_structure()

# ============================================
# Office Detection
# ============================================
MS_OFFICE_AVAILABLE = False
LIBREOFFICE_PATH = None

def find_msoffice():
    """Return true only when Word COM can actually start and quit."""
    if os.name != 'nt':
        return False
    probe = (
        "$ErrorActionPreference = 'Stop'; "
        "$word = New-Object -ComObject Word.Application; "
        "try { $word.Visible = $false } finally { $word.Quit(); "
        "[Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null }"
    )
    try:
        result = subprocess.run(
            ['powershell', '-ExecutionPolicy', 'Bypass', '-NonInteractive', '-NoProfile', '-Command', probe],
            capture_output=True, text=True, timeout=15
        )  # nosec - constant local capability probe
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False

def find_libreoffice():
    """ตรวจหา LibreOffice"""
    possible_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Try finding in PATH
    try:
        result = subprocess.run(['which', 'libreoffice'], capture_output=True, text=True)  # nosec
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    
    return None

# Check available converters
MS_OFFICE_AVAILABLE = find_msoffice()
LIBREOFFICE_PATH = find_libreoffice()

# ============================================
# PDF Conversion Functions
# ============================================

def convert_with_word(word_path, pdf_path):
    """แปลง Word เป็น PDF ผ่าน PowerShell .ps1 temp file (quote-safe)"""
    word_path = os.path.abspath(word_path)
    pdf_path  = os.path.abspath(pdf_path)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    # Clean stale Word lock files in same folder
    folder = os.path.dirname(word_path)
    for f in os.listdir(folder):
        if f.startswith('~$'):
            try: os.remove(os.path.join(folder, f))
            except: pass

    pid_file = word_path + '.word.pid'
    ps_content = f"""$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Win32Pid {{
  [DllImport("user32.dll")]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}}
'@
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {{
    $wordProcessId = 0
    if ($null -ne $word.Hwnd -and [IntPtr]$word.Hwnd -ne [IntPtr]::Zero) {{
        [Win32Pid]::GetWindowThreadProcessId([IntPtr]$word.Hwnd, [ref]$wordProcessId) | Out-Null
        if ($wordProcessId -gt 0) {{ [IO.File]::WriteAllText("{pid_file}", [string]$wordProcessId) }}
    }}
    $doc = $word.Documents.Open("{word_path}", $false, $true, $false)
    $doc.SaveAs([ref]"{pdf_path}", [ref]17)
    $doc.Close([ref]$false)
}} finally {{
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}}
"""
    ps_file = word_path + '.tmp.ps1'
    try:
        with open(ps_file, 'w', encoding='utf-8') as f:
            f.write(ps_content)

        result = subprocess.run(  # nosec
            ['powershell', '-ExecutionPolicy', 'Bypass', '-NonInteractive', '-NoProfile', '-File', ps_file],
            timeout=60,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or 'Word conversion failed').strip()
            print(f"[Word PS error] {err}")
            return False, err
        if not os.path.exists(pdf_path):
            return False, "PDF not created"
        return True, None
    except subprocess.TimeoutExpired:
        try:
            with open(pid_file, 'r', encoding='ascii') as f:
                word_pid = int(f.read().strip())
            subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-Command',
                 (f'Get-Process -Id {word_pid} -ErrorAction SilentlyContinue | '
                  "Where-Object { $_.ProcessName -eq 'WINWORD' } | "
                  'Stop-Process -Force -ErrorAction SilentlyContinue')],
                capture_output=True,
                timeout=10
            )  # nosec - PID belongs to the Word instance started above
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return False, "Word conversion timeout (60s)"
    except Exception as e:
        return False, str(e)
    finally:
        try: os.remove(ps_file)
        except: pass
        try: os.remove(pid_file)
        except: pass

def convert_with_libreoffice(word_path, output_dir, libreoffice_path=None):
    """แปลง Word เป็น PDF ด้วย LibreOffice"""
    try:
        if not libreoffice_path:
            libreoffice_path = LIBREOFFICE_PATH
        
        if not libreoffice_path:
            return False, "LibreOffice not found"
        
        # Ensure paths are absolute
        word_path = os.path.abspath(word_path)
        output_dir = os.path.abspath(output_dir)
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        cmd = [
            libreoffice_path,
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            word_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)  # nosec
        
        if result.returncode != 0:
            return False, result.stderr
        
        return True, None
    except subprocess.TimeoutExpired:
        return False, "Conversion timeout"
    except Exception as e:
        return False, str(e)

def convert_to_pdf(word_path, pdf_path):
    """แปลง Word เป็น PDF โดยเลือก converter ที่เหมาะสม
    Includes auto-retry with re-detection for cross-machine usage."""
    with CONVERSION_LOCK:
        return _convert_to_pdf_locked(word_path, pdf_path)


def _convert_to_pdf_locked(word_path, pdf_path):
    """Run one conversion at a time because local Office automation is not re-entrant."""
    global MS_OFFICE_AVAILABLE, LIBREOFFICE_PATH

    # ---- Attempt 1: Try with cached detection ---------------------------
    success, converter, error = _try_convert(word_path, pdf_path)
    if success:
        return True, converter, None

    # ---- Attempt 2: Re-detect converters (handles new installs / mapped drives)
    print("[INFO] First attempt failed — re-detecting PDF converters...")
    MS_OFFICE_AVAILABLE = find_msoffice()
    LIBREOFFICE_PATH = find_libreoffice()

    success, converter, error = _try_convert(word_path, pdf_path)
    if success:
        return True, converter, None

    # ---- All attempts failed ---------------------------------------------
    hint = (
        "No PDF converter available on this machine. "
        "Install Microsoft Office (+ run INSTALL-MSOFFICE-SUPPORT.bat) "
        "or LibreOffice, then restart the server."
    )
    print(f"[ERROR] {hint}")
    return False, None, hint


def _try_convert(word_path, pdf_path):
    """Internal helper: single conversion attempt using available converters."""
    global MS_OFFICE_AVAILABLE
    # Try MS Office first
    if MS_OFFICE_AVAILABLE:
        success, error = convert_with_word(word_path, pdf_path)
        if success:
            return True, 'MS Office', None
        print(f"[WARNING] MS Office conversion failed: {error}")
        # A successful capability probe should make this rare, but a broken COM
        # path must not delay every subsequent document before LibreOffice runs.
        MS_OFFICE_AVAILABLE = False

    # Try LibreOffice
    if LIBREOFFICE_PATH:
        output_dir = os.path.dirname(pdf_path)
        success, error = convert_with_libreoffice(word_path, output_dir)
        if success:
            source_name = os.path.splitext(os.path.basename(word_path))[0]
            expected_pdf = os.path.join(output_dir, f"{source_name}.pdf")

            if expected_pdf != pdf_path and os.path.exists(expected_pdf):
                shutil.move(expected_pdf, pdf_path)

            return True, 'LibreOffice', None
        print(f"[WARNING] LibreOffice conversion failed: {error}")

    return False, None, "No PDF converter available"

# ============================================
# XML Sanitization
# ============================================

def sanitize_for_xml(value):
    """Sanitize string for safe XML use"""
    if value is None:
        return ''
    
    value = str(value)
    
    # Remove invalid XML characters
    def is_valid_xml_char(c):
        codepoint = ord(c)
        return (
            codepoint == 0x9 or
            codepoint == 0xA or
            codepoint == 0xD or
            (0x20 <= codepoint <= 0xD7FF) or
            (0xE000 <= codepoint <= 0xFFFD) or
            (0x10000 <= codepoint <= 0x10FFFF)
        )
    
    value = ''.join(c for c in value if is_valid_xml_char(c))
    
    # Escape XML special characters (order matters: & first)
    value = value.replace('&', '&amp;')
    value = value.replace('<', '&lt;')
    value = value.replace('>', '&gt;')
    value = value.replace('"', '&quot;')
    value = value.replace("'", '&apos;')
    
    return value

def sanitize_data_for_xml(data):
    """Sanitize all values in dictionary for XML use"""
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_for_xml(value)
        elif isinstance(value, (int, float)):
            sanitized[key] = str(value)
        elif value is None:
            sanitized[key] = ''
        else:
            sanitized[key] = sanitize_for_xml(str(value))
    return sanitized

# ============================================
# Template Processing
# ============================================

def _replace_xml_placeholders(content, data):
    """Replace placeholders without flattening nested text-box paragraphs."""
    replaced_count = 0

    def process_section(section, tag_format):
        nonlocal replaced_count
        t_pattern = r'(<w:t\b[^>]*>)([^<]*)(</w:t>)'
        t_matches = list(re.finditer(t_pattern, section))
        if not t_matches:
            return section
        full_text = ''.join(m.group(2) for m in t_matches)
        full_text = re.sub(r'&lt;\s+', '&lt;', full_text)
        full_text = re.sub(r'\s+&gt;', '&gt;', full_text)
        # The CV Contact template repeats this placeholder in one text box;
        # keep one visible date while retaining the choice/fallback shapes.
        full_text = full_text.replace(
            '&lt;samplingDate&gt;&lt;samplingDate&gt;', '&lt;samplingDate&gt;'
        )
        original = full_text
        for key, value in data.items():
            patterns = [tag_format.format(key)]
            escaped_pattern = f'&lt;{key}&gt;'
            if escaped_pattern not in patterns:
                patterns.append(escaped_pattern)
            for pattern in patterns:
                if pattern in full_text:
                    full_text = full_text.replace(pattern, str(value) if value else '')
                    replaced_count += 1
                    break
        if full_text == original:
            return section
        first_done = [False]

        def replacer(match):
            if not first_done[0]:
                first_done[0] = True
                return match.group(1) + full_text + match.group(3)
            return match.group(1) + match.group(3)

        return re.sub(t_pattern, replacer, section)

    def process_textbox(match):
        textbox = match.group(0)
        return process_section(textbox, '&lt;{}&gt;')

    # Mask processed text boxes while handling ordinary paragraphs. Otherwise
    # the outer paragraph also consumes every nested <w:t> and duplicates text.
    protected = []

    def protect_textbox(match):
        token = f'__ANF3_TEXTBOX_{len(protected)}__'
        protected.append(process_textbox(match))
        return token

    masked = re.sub(
        r'<w:txbxContent>.*?</w:txbxContent>',
        protect_textbox,
        content,
        flags=re.DOTALL
    )
    masked = re.sub(
        r'<w:p\b[^>]*>.*?</w:p>',
        lambda paragraph: process_section(paragraph.group(0), '<{}>'),
        masked,
        flags=re.DOTALL
    )
    for index, textbox in enumerate(protected):
        masked = masked.replace(f'__ANF3_TEXTBOX_{index}__', textbox)
    return masked, replaced_count


def _apply_replacements(content, data):
    """Apply placeholder replacements to XML content string."""
    return _replace_xml_placeholders(content, data)


def _make_ids_unique(xml_fragment, page_idx):
    """Rename anchor/para IDs to avoid duplicates when appending pages."""
    # w:rsidR, w:rsidRDefault, w14:paraId, w14:textId, wp14:anchorId, wp14:editId
    def sub_hex(m):
        return m.group(1) + f'{int(m.group(2), 16) ^ (page_idx * 0x1000):08X}' + m.group(3)
    xml_fragment = re.sub(r'(w14:paraId=")([0-9A-Fa-f]{8})(")', sub_hex, xml_fragment)
    xml_fragment = re.sub(r'(w14:textId=")([0-9A-Fa-f]{8})(")', sub_hex, xml_fragment)
    xml_fragment = re.sub(r'(wp14:anchorId=")([0-9A-Fa-f]{8})(")', sub_hex, xml_fragment)
    xml_fragment = re.sub(r'(wp14:editId=")([0-9A-Fa-f]{8})(")', sub_hex, xml_fragment)
    # Drawing properties use numeric IDs rather than the suffixable VML form.
    # Word requires these IDs to be unique across the assembled document.
    if page_idx > 0:
        original_docpr_ids = {
            int(value) for value in re.findall(r'<wp:docPr\b[^>]*\bid="([0-9]+)"', xml_fragment)
        }
        docpr_index = 0

        def sub_docpr(match):
            nonlocal docpr_index
            docpr_index += 1
            candidate = page_idx * 1_000_000 + docpr_index
            while candidate in original_docpr_ids:
                candidate += 1
            return f'{match.group(1)}{candidate}{match.group(3)}'

        xml_fragment = re.sub(
            r'(<wp:docPr\b[^>]*\bid=")([0-9]+)(")',
            sub_docpr,
            xml_fragment,
        )
    # Compressed Air carries its form artwork as VML. Word requires VML
    # shape, image, and shape-type IDs to be document-unique; duplicated IDs
    # make the repeated background image disappear from later pages. Preserve
    # the authoritative first-page IDs and suffix every later-page reference,
    # including VML type references.
    if page_idx > 0:
        xml_fragment = re.sub(
            r'(_x0000_[sit]\d+)',
            lambda match: f'{match.group(1)}_p{page_idx + 1}',
            xml_fragment,
        )
    return xml_fragment


def build_multipage_docx(template_path, output_path, pages_data):
    """Build a single DOCX with multiple pages by repeating the template body.

    pages_data: list of dicts, one per page (already sanitized).
    Each page's body is appended after a continuous section break from the previous page.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(template_path, 'r') as z:
            z.extractall(temp_dir)

        doc_path = os.path.join(temp_dir, 'word', 'document.xml')
        with open(doc_path, 'r', encoding='utf-8') as f:
            original_xml = f.read()

        body_open = original_xml.find('<w:body>') + len('<w:body>')
        sectPr_start = original_xml.rfind('<w:sectPr')
        body_end = original_xml.find('</w:body>')

        template_body = original_xml[body_open:sectPr_start]   # body content (no sectPr)
        final_sectPr  = original_xml[sectPr_start:body_end]    # last sectPr (keeps page size)
        xml_before    = original_xml[:body_open]
        xml_after     = original_xml[body_end:]

        # Section break paragraph inserted between pages. Copy only the
        # section properties' children; retaining the source closing tag here
        # creates malformed XML and makes Word reject multipage documents.
        sect_pr_end = final_sectPr.rfind('</w:sectPr>')
        sect_pr_children = final_sectPr[final_sectPr.find('>') + 1:sect_pr_end]
        page_break_para = '<w:p><w:pPr><w:sectPr><w:type w:val="nextPage"/>' + \
                          sect_pr_children + \
                          '</w:sectPr></w:pPr></w:p>'

        assembled_parts = []
        for i, page_data in enumerate(pages_data):
            page_xml = _make_ids_unique(template_body, i)
            page_xml, cnt = _apply_replacements(page_xml, page_data)
            print(f"[DEBUG] page {i+1}: {cnt} replacements")
            if i > 0:
                assembled_parts.append(page_break_para)
            assembled_parts.append(page_xml)

        new_xml = xml_before + ''.join(assembled_parts) + final_sectPr + xml_after

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(new_xml)

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for root, dirs, files in os.walk(temp_dir):
                for fname in files:
                    fp = os.path.join(root, fname)
                    zout.write(fp, os.path.relpath(fp, temp_dir))

        return len(pages_data)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def replace_placeholders_in_file(template_path, output_path, data):
    """Replace placeholders in Word document by manipulating XML"""
    
    # Sanitize data first
    data = sanitize_data_for_xml(data)
    
    print(f"[DEBUG] Starting replacement with {len(data)} keys")
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Extract docx
        with zipfile.ZipFile(template_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        replaced_count = 0
        
        # Process document, headers, footers and other Word XML parts. Some
        # controlled templates keep record-level fields in a header/footer;
        # leaving those parts untouched would pass the body-only replacement
        # but still ship literal placeholders in the generated DOCX.
        word_dir = os.path.join(temp_dir, 'word')
        xml_paths = []
        for root, _dirs, files in os.walk(word_dir):
            xml_paths.extend(
                os.path.join(root, name)
                for name in files
                if name.endswith('.xml')
            )
        for xml_path in xml_paths:
            with open(xml_path, 'r', encoding='utf-8') as f:
                content = f.read()

            content, replaced = _replace_xml_placeholders(content, data)
            replaced_count += replaced

            with open(xml_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        print(f"[DEBUG] Total replacements: {replaced_count}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Re-zip
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
        
        return replaced_count
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ============================================
# Helper Functions
# ============================================

def get_form_folder(template_name):
    """Get folder name from template name"""
    if 'pw-prw' in template_name.lower():
        return 'pw-prw'
    elif 'wfi-pus' in template_name.lower():
        return 'wfi-pus'
    elif 'compressed-air' in template_name.lower() or template_name.lower().startswith('ca-'):
        return 'compressed-air'
    elif 'em-air' in template_name.lower() or template_name.lower().startswith('em-'):
        return 'em-air'
    elif 'cleaning' in template_name.lower() or template_name.lower().startswith('cv-'):
        return 'cleaning-validation'
    elif 'growth' in template_name.lower():
        return 'growth-promotion'
    elif 'identification' in template_name.lower() or 'id-' in template_name.lower():
        return 'identification'
    else:
        return 'other'

# ============================================
# Static Files & Routes
# ============================================


# --- choosing a port --------------------------------------------------------
# A laboratory PC often has something else on 8000 already. Failing with
# "Address already in use" and closing the window told the user nothing they
# could act on, so the server now takes the next free port and records it. The
# browser reaches the API on relative paths, so nothing in the app cares which
# port it ended up on; only the launcher needs to know, and it reads the file
# written below.
PORT_FILE = os.path.join(BASE_DIR, '.anf3-port')


def _port_is_free(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
            return True
        except OSError:
            return False


def _pick_free_port(host, preferred, span=40):
    """The preferred port if it is free, else the next free one above it."""
    if _port_is_free(host, preferred):
        return preferred
    for candidate in range(preferred + 1, preferred + span):
        if _port_is_free(host, candidate):
            return candidate
    # Nothing in the range: let the OS choose rather than refuse to start.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


def _write_port_file(port):
    try:
        with open(PORT_FILE, 'w', encoding='utf-8') as handle:
            handle.write(str(port))
    except OSError:
        pass  # a read-only folder must not stop the server starting


def _clear_port_file():
    try:
        os.remove(PORT_FILE)
    except OSError:
        pass


@app.route('/')
def index():
    """Serve only the built application shell."""
    dist_index = os.path.join(DIST_DIR, 'index.html')
    if _is_file_within(dist_index, DIST_DIR):
        return send_file(dist_index, mimetype='text/html')
    return jsonify({'error': 'Frontend build not found'}), 404


def _is_file_within(path, root):
    """Accept regular files only when their resolved target remains under root."""
    try:
        resolved_path = os.path.realpath(path)
        resolved_root = os.path.realpath(root)
        return (os.path.commonpath([resolved_root, resolved_path]) == resolved_root and
                os.path.isfile(resolved_path))
    except ValueError:
        return False

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from BASE_DIR"""
    normalized = filename.replace('\\', '/')
    legacy_html = any(
        normalized == f'{folder}/{page}.html'
        for folder in LEGACY_PAGE_FOLDERS
        for page in ('list', 'menu', 'print')
    )
    shared_asset = (
        (normalized.startswith('js/') and normalized.endswith('.js')) or
        normalized == 'css/style.css'
    )
    dist_candidate = os.path.abspath(os.path.join(DIST_DIR, normalized))
    dist_asset = _is_file_within(dist_candidate, DIST_DIR)
    inventory_pdf = normalized == 'inventory_catalog.pdf'
    inventory_index = normalized == 'catalog/inventory-index.json'
    # Runtime configuration lives beside the launchers, NOT inside dist/:
    # `pnpm build` empties dist/, so a copy in there would be silently reset on
    # every rebuild and the owner would lose the URLs they pasted in. It holds
    # public read endpoints only -- never ANF3_SYNC_TOKEN.
    runtime_config = normalized == 'config.json'
    if '..' in normalized.split('/') or not (legacy_html or shared_asset or dist_asset
                                             or inventory_pdf or inventory_index or runtime_config):
        return jsonify({'error': 'Not found'}), 404
    
    # Vite emits the React shell into dist/. Keep legacy files at the project
    # root so existing form/list/print links remain stable.
    dist_path = os.path.join(DIST_DIR, filename)
    file_path = dist_path if os.path.isfile(dist_path) else os.path.join(BASE_DIR, filename)
    if runtime_config:
        file_path = os.path.join(BASE_DIR, 'config.json')
    if inventory_pdf:
        file_path = INVENTORY_PDF
    elif inventory_index:
        file_path = next((path for path in INVENTORY_INDEX_PATHS if os.path.isfile(path)), '')

    if filename == 'index.html' and os.path.isfile(os.path.join(DIST_DIR, 'index.html')):
        file_path = os.path.join(DIST_DIR, 'index.html')
    
    # If it's a directory, try to serve index.html
    if os.path.isdir(file_path):
        index_path = os.path.join(file_path, 'index.html')
        if os.path.isfile(index_path):
            return send_file(index_path, mimetype='text/html')
        return jsonify({'error': 'Directory listing not allowed'}), 403
    
    if _is_file_within(file_path, BASE_DIR):
        # Determine MIME type
        if filename.endswith('.html'):
            mimetype = 'text/html'
        elif filename.endswith('.css'):
            mimetype = 'text/css'
        elif filename.endswith('.js') or filename.endswith('.mjs'):
            # .mjs matters: a browser applies strict MIME checking to module
            # scripts and refuses one served as application/octet-stream, which
            # is what Flask guesses for an unknown extension. The pdf.js worker
            # ships as .mjs, so without this the print preview cannot draw a
            # single page -- it fails with "Expected a JavaScript-or-Wasm
            # module script" and silently falls back to a fake worker.
            mimetype = 'text/javascript'
        elif filename.endswith('.json'):
            mimetype = 'application/json'
        elif filename.endswith('.png'):
            mimetype = 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            mimetype = 'image/jpeg'
        elif filename.endswith('.svg'):
            mimetype = 'image/svg+xml'
        elif filename.endswith('.woff') or filename.endswith('.woff2'):
            mimetype = 'font/woff2'
        elif filename.endswith('.docx'):
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif filename.endswith('.pdf'):
            mimetype = 'application/pdf'
        else:
            mimetype = 'application/octet-stream'
        
        return send_file(file_path, mimetype=mimetype)
    
    return jsonify({'error': 'File not found'}), 404


def _json_error(message, status_code):
    return jsonify({'error': message}), status_code


def _workflow_config(payload):
    workflow = payload.get('workflow') or payload.get('formType')
    if not isinstance(workflow, str) or workflow not in PDF_WORKFLOW_REGISTRY:
        raise ValueError('Unsupported workflow')
    return workflow, PDF_WORKFLOW_REGISTRY[workflow]['template']


def _normalize_cv_token(value):
    return re.sub(r'[\s_.-]+', '', str(value or '').strip().upper())


def _cv_sampling_family(payload, document_data):
    context = payload.get('cvContext') if isinstance(payload.get('cvContext'), dict) else {}
    raw = (context.get('samplingFamily') or context.get('sampleMatrix') or
           document_data.get('samplingFamily') or document_data.get('sampleMatrix') or
           document_data.get('sampleType') or document_data.get('cvType'))
    token = _normalize_cv_token(raw)
    if 'CONTACTPLATE' in token or token == 'CONTACT':
        return 'contact-plate'
    if 'RINSE' in token:
        return 'rinse'
    return 'unknown'


def _cv_test_method(payload, document_data):
    context = payload.get('cvContext') if isinstance(payload.get('cvContext'), dict) else {}
    raw = (context.get('testMethod') or context.get('method') or
           document_data.get('testMethod') or document_data.get('method'))
    token = _normalize_cv_token(raw)
    if 'POURPLATE' in token or token == 'POUR':
        return 'pour-plate'
    if ('MEMBRANEFILTRATION' in token or token == 'MEMBRANE' or
            token == 'MEMBFILTRATION'):
        return 'membrane-filtration'
    return 'unknown'


def _validate_pdf_route(workflow, payload, document_data):
    """Validate the controlled CV route independently of the browser."""
    if not workflow.startswith('cleaning-validation-'):
        return
    family = _cv_sampling_family(payload, document_data)
    method = _cv_test_method(payload, document_data)
    if family == 'unknown':
        raise ValueError('CV sampling family is required')
    if workflow == 'cleaning-validation-contact':
        if family != 'contact-plate':
            raise ValueError('Contact route accepts Contact Plate records only')
        return
    if family != 'rinse':
        raise ValueError('CV Rinse routes accept Rinse records only')
    expected_method = PDF_WORKFLOW_REGISTRY[workflow].get('testMethod')
    if method == 'unknown' or method != expected_method:
        raise ValueError('CV Rinse test method does not match the selected route')


def _hash_file(path):
    try:
        stat = os.stat(path)
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = TEMPLATE_HASH_CACHE.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
    except OSError:
        stamp = None
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    result = digest.hexdigest()
    if stamp is not None:
        TEMPLATE_HASH_CACHE[path] = (stamp, result)
    return result


def _backup_pending_path(pdf_id):
    if not PDF_ID_RE.fullmatch(str(pdf_id or '')):
        return None
    return os.path.join(BACKUP_SPOOL_DIR, f'{pdf_id}.json')


def _path_within(path, root):
    try:
        return os.path.commonpath([os.path.realpath(root), os.path.realpath(path)]) == os.path.realpath(root)
    except ValueError:
        return False


def _lock_file_handle(handle):
    """Best-effort cross-process exclusive lock for the open file handle."""
    if msvcrt is None:
        return
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    except OSError:
        pass


def _unlock_file_handle(handle):
    """Release a lock obtained by _lock_file_handle."""
    if msvcrt is None:
        return
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


@contextmanager
def _worksheet_file_lock(workflow, worksheet_no):
    """Serialize multi-PC access to one worksheet's controlled artifacts."""
    if not PROJECT_SHARE_ROOT or not SAFE_KEY_RE.fullmatch(str(workflow or '')) or not SAFE_KEY_RE.fullmatch(str(worksheet_no or '')):
        yield
        return
    lock_dir = os.path.join(PROJECT_SHARE_ROOT, '.locks', workflow)
    lock_path = os.path.join(lock_dir, f'{worksheet_no}.lock')
    try:
        os.makedirs(lock_dir, exist_ok=True)
    except OSError:
        yield
        return
    try:
        with open(lock_path, 'a') as lock_file:
            _lock_file_handle(lock_file)
            try:
                yield
            finally:
                _unlock_file_handle(lock_file)
    except OSError:
        yield


def _ensure_project_share():
    """Make the configured share writable before any controlled rendering."""
    root = str(PROJECT_SHARE_ROOT or '').strip()
    if not root:
        return False
    try:
        os.makedirs(root, exist_ok=True)
        if not os.path.isdir(root):
            return False
        activity_log.configure_project_share(root)
        return True
    except OSError:
        return False


def _share_artifact_paths(workflow, worksheet_no):
    if (not PROJECT_SHARE_ROOT or not SAFE_KEY_RE.fullmatch(str(workflow or '')) or
            not SAFE_KEY_RE.fullmatch(str(worksheet_no or ''))):
        return None
    word_relative = os.path.join('words', workflow, f'{worksheet_no}.docx')
    pdf_relative = os.path.join('pdfs', workflow, f'{worksheet_no}.pdf')
    metadata_relative = os.path.join('manifests', workflow, worksheet_no, f'{worksheet_no}.json')
    paths = {
        'word': os.path.join(PROJECT_SHARE_ROOT, word_relative),
        'pdf': os.path.join(PROJECT_SHARE_ROOT, pdf_relative),
        'metadata': os.path.join(PROJECT_SHARE_ROOT, metadata_relative),
        'wordRelativePath': word_relative,
        'pdfRelativePath': pdf_relative,
        'metadataRelativePath': metadata_relative,
    }
    if not all(_path_within(paths[key], PROJECT_SHARE_ROOT) for key in ('word', 'pdf', 'metadata')):
        return None
    return paths


def _share_metadata(workflow, worksheet_no):
    paths = _share_artifact_paths(workflow, worksheet_no)
    if not paths or not _is_nonempty_file(paths['metadata']):
        return None, paths
    try:
        with open(paths['metadata'], 'r', encoding='utf-8') as source:
            metadata = json.load(source)
    except (OSError, ValueError, TypeError):
        return None, paths
    if not isinstance(metadata, dict):
        return None, paths
    return metadata, paths


def _share_entry_is_current(workflow, worksheet_no, pdf_id):
    metadata, paths = _share_metadata(workflow, worksheet_no)
    if not metadata or not paths:
        return False
    try:
        pdf_fp = _artifact_fingerprint(paths['pdf'])
        word_fp = _artifact_fingerprint(paths['word'])
    except OSError:
        return False
    return (
        metadata.get('pdfId') == pdf_id and
        metadata.get('workflow') == workflow and
        metadata.get('worksheetNo') == worksheet_no and
        metadata.get('filename') == f'{worksheet_no}.pdf' and
        metadata.get('status') == 'ready' and
        metadata.get('rendererVersion') == DOCX_RENDERER_VERSION and
        metadata.get('wordSha256') == word_fp['sha256'] and
        metadata.get('pdfSha256') == pdf_fp['sha256'] and
        metadata.get('wordSize') == word_fp['size'] and
        metadata.get('pdfSize') == pdf_fp['size'] and
        _is_valid_pdf(paths['pdf']) and
        zipfile.is_zipfile(paths['word'])
    )


def _archive_existing_share_version(workflow, worksheet_no, pdf_id):
    """Keep a replaced controlled set in the share history before promotion."""
    metadata, paths = _share_metadata(workflow, worksheet_no)
    if not metadata or not paths or metadata.get('pdfId') == pdf_id:
        return
    previous_id = str(metadata.get('pdfId') or '')
    if not PDF_ID_RE.fullmatch(previous_id):
        previous_id = 'previous'
    history_root = os.path.join(PROJECT_SHARE_ROOT, 'history', workflow, worksheet_no, previous_id)
    for kind, source, filename in (
        ('word', paths['word'], f'{worksheet_no}.docx'),
        ('pdf', paths['pdf'], f'{worksheet_no}.pdf'),
        ('metadata', paths['metadata'], f'{worksheet_no}.json'),
    ):
        expected = _artifact_fingerprint(source)
        _copy_verified(source, os.path.join(history_root, filename), expected)


def _unique_share_stage_path(destination):
    """Return a unique staging path on the same volume as the final file.

    Promotion uses os.replace(), which on Windows raises WinError 17
    (ERROR_NOT_SAME_DEVICE / errno EXDEV) when source and destination are on
    different logical volumes. Staging the generated artifact next to its
    final controlled name keeps every promotion inside one volume.
    """
    return os.path.join(
        os.path.dirname(destination),
        f'.{os.path.basename(destination)}.{uuid.uuid4().hex}.part'
    )


def _stage_share_artifact(source, destination):
    """Copy one generated artifact to a verified same-volume staging file.

    The staged file is uniquely named so a crashed or concurrent publisher can
    never reuse or clobber it. Existence, size and content hash are verified
    before the caller is allowed to promote it. Any partially copied staging
    file is removed on failure.
    """
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temporary = _unique_share_stage_path(destination)
    try:
        expected = _artifact_fingerprint(source)
        shutil.copy2(source, temporary)
        if not _is_nonempty_file(temporary) or _artifact_fingerprint(temporary) != expected:
            raise OSError(f'Project share copy failed integrity check: {destination}')
        return temporary, destination, expected
    except Exception:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass
        raise


def _artifact_fingerprint(path):
    if not _is_nonempty_file(path):
        raise OSError(f'Artifact is missing or empty: {path}')
    return {'size': os.path.getsize(path), 'sha256': _hash_file(path)}


def _backup_event(action, worksheet_no, detail):
    # Backup attribution is server-generated and is never treated as a
    # signature or authentication event. The reason is logged server-side only.
    _entry, _reason = activity_log.record(action=action, worksheet_no=worksheet_no, detail=detail)


def _write_json_atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f'{path}.part'
    with open(temporary, 'w', encoding='utf-8') as target:
        json.dump(value, target, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    os.replace(temporary, path)


def _copy_verified(source, destination, expected, replace=False):
    if not _path_within(destination, PROJECT_SHARE_ROOT):
        raise ValueError('Project share destination escapes the configured root')
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.exists(destination):
        actual = _artifact_fingerprint(destination)
        if actual != expected:
            if not replace:
                raise ValueError(f'Project share already contains different content: {destination}')
        else:
            return

    temporary = f'{destination}.part'
    try:
        shutil.copy2(source, temporary)
        if _artifact_fingerprint(temporary) != expected:
            raise ValueError(f'Project share copy failed integrity check: {destination}')
        if os.path.exists(destination):
            actual = _artifact_fingerprint(destination)
            if actual != expected:
                if not replace:
                    raise ValueError(f'Project share already contains different content: {destination}')
                os.replace(temporary, destination)
            else:
                os.remove(temporary)
        else:
            os.replace(temporary, destination)
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def _backup_manifest(workflow, worksheet_no, pdf_id, word_path, pdf_path, metadata_path):
    with open(metadata_path, 'r', encoding='utf-8') as source:
        metadata = json.load(source)
    if (metadata.get('pdfId') != pdf_id or metadata.get('workflow') != workflow or
            metadata.get('worksheetNo') != worksheet_no or
            metadata.get('filename') != f'{worksheet_no}.pdf'):
        raise ValueError('Generated artifact metadata does not match worksheet identity')

    artifacts = []
    for kind, source_path, relative_path in (
        ('docx', word_path, os.path.join('words', workflow, f'{worksheet_no}.docx')),
        ('pdf', pdf_path, os.path.join('pdfs', workflow, f'{worksheet_no}.pdf')),
        ('metadata', metadata_path, os.path.join('manifests', workflow, worksheet_no, f'{worksheet_no}.json')),
    ):
        fingerprint = _artifact_fingerprint(source_path)
        artifacts.append({
            'kind': kind,
            'source': os.path.abspath(source_path),
            'relativePath': relative_path,
            **fingerprint,
        })
    return {
        'schemaVersion': 1,
        'workflow': workflow,
        'worksheetNo': worksheet_no,
        'pdfId': pdf_id,
        'historyRoot': os.path.join('history', workflow, worksheet_no),
        'artifacts': artifacts,
    }


def _existing_share_pdf_id(workflow, worksheet_no, current_pdf_id):
    metadata_path = os.path.join(
        PROJECT_SHARE_ROOT, 'manifests', workflow, worksheet_no, f'{worksheet_no}.json'
    )
    try:
        with open(metadata_path, 'r', encoding='utf-8') as source:
            metadata = json.load(source)
        previous = str(metadata.get('pdfId') or '')
        if PDF_ID_RE.fullmatch(previous):
            return previous if previous != current_pdf_id else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return 'previous'


def _preserve_existing_share_artifacts(manifest):
    """Archive a different worksheet version before replacing share primaries."""
    workflow = str(manifest.get('workflow') or '')
    worksheet_no = str(manifest.get('worksheetNo') or '')
    current_pdf_id = str(manifest.get('pdfId') or '')
    current, _paths = _share_metadata(workflow, worksheet_no)
    if not current or current.get('pdfId') == current_pdf_id:
        return
    previous_pdf_id = str(current.get('pdfId') or '')
    if not PDF_ID_RE.fullmatch(previous_pdf_id):
        previous_pdf_id = 'previous'
    history_root = os.path.join(
        PROJECT_SHARE_ROOT, str(manifest.get('historyRoot') or os.path.join('history', workflow, worksheet_no)),
        previous_pdf_id
    )
    for artifact in manifest.get('artifacts', []):
        relative_path = str(artifact.get('relativePath') or '')
        destination = os.path.join(PROJECT_SHARE_ROOT, relative_path)
        if not _path_within(destination, PROJECT_SHARE_ROOT) or not _is_nonempty_file(destination):
            continue
        actual = _artifact_fingerprint(destination)
        history_path = os.path.join(history_root, os.path.basename(relative_path))
        _copy_verified(destination, history_path, actual)


def _publish_manifest(manifest):
    """Publish the complete DOCX/PDF/manifest set to the Share.

    Generated artifacts live in the local OS temp directory while the Share is
    a different logical volume, so a file must never be moved directly from
    one to the other (Windows WinError 17 / errno EXDEV). Every artifact is
    first copied to a uniquely named staging file in the same directory as its
    final controlled name, verified for existence, size and content hash, and
    only then promoted with same-volume os.replace() calls. DOCX and PDF are
    promoted first; the metadata file is written last as the commit record.
    If any step fails, every promotion is rolled back so a torn set can never
    be treated as the current worksheet version. Leftover staging files carry
    hidden unique .part names that no reader treats as a valid document.
    """
    if not _ensure_project_share():
        raise OSError('Project share is unavailable')

    artifacts_by_kind = {}
    for artifact in manifest.get('artifacts', []):
        source = str(artifact.get('source') or '')
        destination = os.path.join(PROJECT_SHARE_ROOT, str(artifact.get('relativePath') or ''))
        if (not source or not _path_within(destination, PROJECT_SHARE_ROOT) or
                _artifact_fingerprint(source) != {
                    'size': int(artifact.get('size', 0)),
                    'sha256': str(artifact.get('sha256') or '')
                }):
            raise ValueError(f'Generated artifact changed or is unavailable: {source}')
        artifacts_by_kind[str(artifact.get('kind') or '')] = (source, destination)

    if not all(kind in artifacts_by_kind for kind in ('docx', 'pdf', 'metadata')):
        raise ValueError('Manifest is missing one or more controlled artifacts')

    data_artifacts = [artifacts_by_kind['docx'], artifacts_by_kind['pdf']]
    commit_source, commit_destination = artifacts_by_kind['metadata']

    staged = []
    backups = []
    promoted = []
    try:
        with BACKUP_LOCK:
            # Stage and verify every byte on the Share volume first. All staging
            # is same-volume, so a failed copy or a disappeared share cannot
            # disturb the current worksheet version.
            for source, destination in data_artifacts + [(commit_source, commit_destination)]:
                staged.append(_stage_share_artifact(source, destination))

            _preserve_existing_share_artifacts(manifest)

            # Promote DOCX and PDF first; every move is within one volume.
            for temporary, destination, _expected in staged:
                if destination == commit_destination:
                    continue
                backup = f'{destination}.rollback'
                if os.path.exists(backup):
                    os.remove(backup)
                if os.path.exists(destination):
                    os.replace(destination, backup)
                    backups.append((backup, destination))
                os.replace(temporary, destination)
                promoted.append(destination)

            # Metadata is the commit record: promote it only after DOCX/PDF.
            commit_temporary = next(temporary for temporary, destination, _expected in staged if destination == commit_destination)
            commit_backup = f'{commit_destination}.rollback'
            if os.path.exists(commit_backup):
                os.remove(commit_backup)
            if os.path.exists(commit_destination):
                os.replace(commit_destination, commit_backup)
                backups.append((commit_backup, commit_destination))
            os.replace(commit_temporary, commit_destination)
            promoted.append(commit_destination)
    except (OSError, ValueError, KeyError, TypeError):
        # Roll back every promoted artifact if the commit did not complete.
        for destination in reversed(promoted):
            try:
                if os.path.exists(destination):
                    os.remove(destination)
            except OSError:
                pass
        for backup, destination in reversed(backups):
            try:
                if os.path.exists(backup):
                    os.replace(backup, destination)
            except OSError:
                pass
        raise
    finally:
        # The Share can disappear mid-operation; cleanup is best-effort.
        # Remaining files carry unique hidden .part names that are never read
        # as controlled documents.
        for temporary, _destination, _expected in staged:
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass

    for backup, _destination in backups:
        try:
            if os.path.exists(backup):
                os.remove(backup)
        except OSError:
            pass


def _attempt_backup(manifest, retry=False):
    worksheet_no = str(manifest.get('worksheetNo') or '')
    pdf_id = str(manifest.get('pdfId') or '')
    if not PROJECT_SHARE_ROOT:
        return {'status': 'failed', 'configured': False, 'pdfId': pdf_id, 'error': 'Project share is not configured'}
    if not PDF_ID_RE.fullmatch(pdf_id) or not SAFE_KEY_RE.fullmatch(worksheet_no):
        raise ValueError('Invalid backup identity')
    if retry:
        _backup_event('backup_retried', worksheet_no, f'{manifest.get("workflow", "")}/{pdf_id}')

    try:
        _publish_manifest(manifest)
        _backup_event('backup_succeeded', worksheet_no, f'{manifest.get("workflow", "")}/{pdf_id}')
        return {'status': 'succeeded', 'configured': True, 'pdfId': pdf_id}
    except (OSError, ValueError, KeyError, TypeError) as error:
        _backup_event('backup_failed', worksheet_no, str(error))
        return {'status': 'failed', 'configured': True, 'pdfId': pdf_id, 'error': str(error)}


def _backup_artifacts(workflow, worksheet_no, pdf_id, word_path, pdf_path, metadata_path, retry=False):
    if not PROJECT_SHARE_ROOT:
        return {'status': 'failed', 'configured': False, 'pdfId': pdf_id, 'error': 'Project share is not configured'}
    try:
        manifest = _backup_manifest(workflow, worksheet_no, pdf_id, word_path, pdf_path, metadata_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        _backup_event('backup_failed', worksheet_no, str(error))
        return {'status': 'failed', 'configured': True, 'pdfId': pdf_id, 'error': str(error)}
    return _attempt_backup(manifest, retry=retry)


def _retry_pending(pdf_id):
    pending = _backup_pending_path(pdf_id)
    if not pending or not os.path.isfile(pending):
        return {'status': 'not-pending', 'configured': bool(PROJECT_SHARE_ROOT), 'pdfId': pdf_id}
    try:
        with open(pending, 'r', encoding='utf-8') as source:
            manifest = json.load(source)
    except (OSError, ValueError) as error:
        return {'status': 'failed', 'configured': bool(PROJECT_SHARE_ROOT), 'pdfId': pdf_id, 'error': str(error)}
    return _attempt_backup(manifest, retry=True)


def _unresolved_placeholders(path):
    """Return literal placeholders left in any generated Word XML part."""
    try:
        with zipfile.ZipFile(path) as archive:
            xml_parts = [
                name for name in archive.namelist()
                if name.startswith('word/') and name.endswith('.xml')
            ]
            if 'word/document.xml' not in xml_parts:
                return ['document.xml unavailable']
            contents = [archive.read(name).decode('utf-8') for name in xml_parts]
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError):
        return ['document.xml unavailable']

    text = re.sub(r'<[^>]+>', '', '\n'.join(contents))
    placeholders = re.findall(r'<[A-Za-z][A-Za-z0-9 ]*>', text)
    placeholders.extend(re.findall(r'&lt;([A-Za-z][A-Za-z0-9 ]*)&gt;', text))
    return sorted(set(placeholders))


def _is_nonempty_file(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def _is_valid_pdf(path):
    """Reject non-empty cache files that are not complete PDF containers."""
    try:
        with open(path, 'rb') as source:
            if source.read(5) != b'%PDF-':
                return False
            source.seek(-min(1024, os.path.getsize(path)), os.SEEK_END)
            return b'%%EOF' in source.read()
    except (OSError, ValueError):
        return False


def _cache_entry_is_current(workflow, worksheet_no, pdf_id, pdf_path,
                            metadata_path, word_path):
    if not (_is_valid_pdf(pdf_path) and _is_nonempty_file(metadata_path)
            and _is_nonempty_file(word_path)):
        return False
    if not zipfile.is_zipfile(word_path):
        return False
    try:
        with open(metadata_path, 'r', encoding='utf-8') as source:
            metadata = json.load(source)
        if not isinstance(metadata, dict):
            return False
        return (
            metadata.get('pdfId') == pdf_id and
            metadata.get('workflow') == workflow and
            metadata.get('filename') == f'{worksheet_no}.pdf' and
            metadata.get('status') == 'ready' and
            metadata.get('rendererVersion') == DOCX_RENDERER_VERSION
        )
    except (OSError, ValueError, zipfile.BadZipFile):
        return False


def _worksheet_artifact_conflicts(workflow, worksheet_no, pdf_id):
    """Return ready Share artifact ids for this worksheet with different content."""
    folder = os.path.join(PROJECT_SHARE_ROOT, 'manifests', workflow)
    if not PROJECT_SHARE_ROOT or not os.path.isdir(folder):
        return []
    conflicts = []
    for worksheet_folder in os.listdir(folder):
        metadata_path = os.path.join(folder, worksheet_folder, f'{worksheet_folder}.json')
        if worksheet_folder != worksheet_no or not _path_within(metadata_path, folder):
            continue
        try:
            with open(metadata_path, encoding='utf-8') as source:
                metadata = json.load(source)
        except (OSError, ValueError):
            continue
        if (metadata.get('status') == 'ready' and
                metadata.get('filename') == f'{worksheet_no}.pdf' and
                PDF_ID_RE.fullmatch(str(metadata.get('pdfId') or '')) and
                metadata.get('pdfId') != pdf_id):
            conflicts.append(metadata.get('pdfId'))
    return sorted(conflicts)


def _field_hashes(document_data):
    """Keep conflict comparison auditable without storing printable values."""
    return {
        str(key): hashlib.sha256(json.dumps(value, ensure_ascii=False,
                                             sort_keys=True,
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
        for key, value in document_data.items()
    }


def _worksheet_changed_fields(workflow, conflict_ids, document_data):
    current = _field_hashes(document_data)
    changed = set()
    for conflict_id in conflict_ids:
        metadata, _path = _load_pdf_metadata(conflict_id)
        previous = metadata.get('fieldHashes') if isinstance(metadata, dict) else None
        if not isinstance(previous, dict):
            changed.update(current)
            continue
        changed.update(key for key in set(current) | set(previous)
                       if current.get(key) != previous.get(key))
    return sorted(changed)


def _pdf_paths(workflow, pdf_id):
    if not PDF_ID_RE.fullmatch(pdf_id or ''):
        return None, None
    folder = os.path.join(PDFS_DIR, workflow)
    return os.path.join(folder, f'{pdf_id}.pdf'), os.path.join(folder, f'{pdf_id}.json')


def _safe_pdf_filename(value):
    if not isinstance(value, str) or value != os.path.basename(value):
        return None
    if not value.lower().endswith('.pdf') or value.endswith((' ', '.')):
        return None
    stem = value[:-4].rstrip(' .')
    if not stem or stem != value[:-4] or stem.upper() in WINDOWS_DEVICE_NAMES:
        return None
    return value


def _replace_artifact_set(promotions, removals):
    """Promote a completed document set, restoring every prior byte on failure."""
    backups = []
    staged = []

    def safe_remove(path):
        try:
            os.remove(path)
        except OSError:
            # A failed cleanup must not strand a .rollback sidecar when the
            # primary remove operation was interrupted or fault-injected.
            os.unlink(path)

    try:
        for source, destination in promotions:
            backup = destination + '.rollback'
            if os.path.exists(destination):
                os.replace(destination, backup)
                backups.append((backup, destination))
            os.replace(source, destination)
            staged.append(destination)
        for path in removals:
            if os.path.exists(path):
                backup = path + '.rollback'
                os.replace(path, backup)
                backups.append((backup, path))
    except OSError:
        for destination in reversed(staged):
            try:
                if os.path.exists(destination):
                    safe_remove(destination)
            except OSError:
                pass
        for backup, destination in reversed(backups):
            try:
                if os.path.exists(backup):
                    os.replace(backup, destination)
            except OSError:
                pass
        raise

    # Reaching this point means the new DOCX/PDF/metadata set is complete.
    # Cleanup is deliberately best-effort: a superseded artifact may remain
    # usable, but it must never make the new set inconsistent or return 500.
    for backup, _destination in backups:
        try:
            if os.path.exists(backup):
                safe_remove(backup)
        except OSError:
            pass


def _load_pdf_metadata(pdf_id):
    if not PROJECT_SHARE_ROOT or not PDF_ID_RE.fullmatch(str(pdf_id or '')):
        return None, None
    for workflow in WORKFLOW_TEMPLATES:
        manifest_root = os.path.join(PROJECT_SHARE_ROOT, 'manifests', workflow)
        if not os.path.isdir(manifest_root):
            continue
        try:
            worksheet_folders = os.listdir(manifest_root)
        except OSError:
            continue
        for worksheet_no in worksheet_folders:
            metadata, paths = _share_metadata(workflow, worksheet_no)
            if not metadata or not paths:
                continue
            if (metadata.get('pdfId') == pdf_id and
                    metadata.get('workflow') == workflow and
                    metadata.get('status') == 'ready' and
                    _safe_pdf_filename(metadata.get('filename')) and
                    _is_valid_pdf(paths['pdf'])):
                return metadata, paths['pdf']
    return None, None


@app.errorhandler(413)
def request_too_large(_error):
    return _json_error('Request body exceeds the 2 MB limit', 413)


@app.route('/api/catalog/status', methods=['GET'])
def catalog_status():
    available = os.path.isfile(INVENTORY_PDF)
    actual_hash = _hash_file(INVENTORY_PDF).upper() if available else None
    manifest_path = next((path for path in INVENTORY_INDEX_PATHS if os.path.isfile(path)), '')
    row_count = 0
    index_hash = None
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as source:
                manifest = json.load(source)
            index_hash = str(manifest.get('sourceSha256') or manifest.get('source', {}).get('sha256') or '').upper()
            rows = manifest.get('items') or manifest.get('rows') or []
            row_count = len(rows) if isinstance(rows, list) else 0
        except (OSError, ValueError, AttributeError):
            index_hash = None
    hash_matches = bool(available and actual_hash == INVENTORY_INDEX_HASH and index_hash == INVENTORY_INDEX_HASH)
    return jsonify({
        'available': available,
        'indexAvailable': hash_matches and row_count == 95,
        'hashMatches': hash_matches,
        'expectedHash': INVENTORY_INDEX_HASH,
        'actualHash': actual_hash,
        'rowCount': row_count,
        'pdfUrl': '/inventory_catalog.pdf',
        'indexUrl': '/catalog/inventory-index.json'
    })


@app.route('/api/pdf-capabilities', methods=['GET'])
def pdf_capabilities():
    """Expose safe, server-owned template capability metadata to the UI."""
    capabilities = []
    for workflow, config in PDF_WORKFLOW_REGISTRY.items():
        template_path = os.path.join(TEMPLATE_DIR, config['template'])
        installed = os.path.isfile(template_path) and zipfile.is_zipfile(template_path)
        capabilities.append({
            'workflow': workflow,
            'enabled': installed,
            'owner': config['owner'],
            'family': config['family'],
            'sourceWorkflow': config.get('sourceWorkflow'),
            'templateHash': _hash_file(template_path) if installed else None
        })
    return jsonify({'ok': True, 'capabilities': capabilities})


@app.route('/api/pdfs', methods=['POST'])
def create_pdf():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error('A JSON object is required', 400)
    try:
        workflow, template_name = _workflow_config(payload)
    except ValueError as error:
        return _json_error(str(error), 400)

    worksheet_no = str(payload.get('worksheetNo') or payload.get('documentNo') or 'preview').strip()
    if (not SAFE_KEY_RE.fullmatch(worksheet_no) or
            worksheet_no.rstrip(' .').upper() in WINDOWS_DEVICE_NAMES):
        return _json_error('Invalid worksheet number', 400)

    pages = payload.get('pages')
    document_data = payload.get('data') or payload.get('record') or payload.get('tags') or {}
    if pages is not None and (not isinstance(pages, list) or not pages or
                              not all(isinstance(page, dict) for page in pages)):
        return _json_error('pages must be a non-empty array of objects', 400)
    if not isinstance(document_data, dict):
        return _json_error('data must be an object', 400)

    capacities = {
        'pw-prw': 30, 'wfi-pus': 30, 'compressed-air': 10, 'em-air': 50,
        'cleaning-validation-contact': 10,
        'cleaning-validation-rinse-pour': 30,
        'cleaning-validation-rinse-membrane': 30,
    }
    try:
        sample_count = int(document_data.get('sampleCount', 0) or 0)
    except (TypeError, ValueError):
        sample_count = 0
    if sample_count > capacities.get(workflow, 0) and not pages:
        return _json_error('Record exceeds the approved template capacity; split it into pages before generating', 422)

    try:
        _validate_pdf_route(workflow, payload, document_data)
    except ValueError as error:
        return _json_error(str(error), 422)

    template_path = os.path.join(TEMPLATE_DIR, template_name)
    if not os.path.isfile(template_path):
        return _json_error('PDF template is not installed for this workflow', 503)

    template_hash = _hash_file(template_path)
    cache_input = {
        'workflow': workflow,
        'worksheetNo': worksheet_no,
        'data': document_data,
        'pages': pages,
        'templateHash': template_hash
    }
    content = json.dumps(cache_input, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    pdf_id = hashlib.sha256(content).hexdigest()
    if not _ensure_project_share():
        return _json_error('Project share is unavailable; the worksheet was not saved', 503)
    share_paths = _share_artifact_paths(workflow, worksheet_no)
    if not share_paths:
        return _json_error('Project share path is invalid', 503)
    regeneration = payload.get('regeneration') or {}
    replace_requested = regeneration.get('mode') == 'replace'
    requested_pdf_id = str(regeneration.get('requestedPdfId') or '')
    supplied_existing_ids = regeneration.get('existingPdfIds')

    # The worksheet identity is user-facing and must never be silently
    # overwritten by two concurrent requests. Serialize the identity check,
    # DOCX write, conversion and metadata commit as one transaction, first
    # across PCs via a share lock file, then across threads in this process.
    with _worksheet_file_lock(workflow, worksheet_no):
        with DOCUMENT_GENERATION_LOCK:
            existing_ids = _worksheet_artifact_conflicts(workflow, worksheet_no, pdf_id)
            changed_fields = _worksheet_changed_fields(workflow, existing_ids, document_data) if existing_ids else []
            if existing_ids:
                valid_replace = (
                    replace_requested and
                    requested_pdf_id == pdf_id and
                    isinstance(supplied_existing_ids, list) and
                    sorted(str(value) for value in supplied_existing_ids) == existing_ids
                )
                if not valid_replace:
                    return jsonify({
                        'error': 'Worksheet already has a generated document with different content; review and confirm replacement',
                        'code': 'WORKSHEET_CONTENT_CONFLICT',
                        'worksheetNo': worksheet_no,
                        'workflow': workflow,
                        'requestedPdfId': pdf_id,
                        'existingPdfIds': existing_ids,
                        'changedFields': changed_fields
                    }), 409

            # A Share metadata/PDF/DOCX set is the only persistent cache. Local
            # hash-named files are never treated as controlled artifacts.
            if _share_entry_is_current(workflow, worksheet_no, pdf_id):
                return jsonify({'pdfId': pdf_id, 'status': 'ready', 'cached': True,
                                'backup': {'status': 'succeeded', 'configured': True, 'pdfId': pdf_id}})

            temporary_dir = tempfile.mkdtemp(prefix='anf3-pdf-')
            temporary_word = os.path.join(temporary_dir, f'{worksheet_no}.docx')
            temporary_pdf = os.path.join(temporary_dir, f'{pdf_id}.pdf')
            temporary_metadata = os.path.join(temporary_dir, f'{pdf_id}.json')
            try:
                if pages:
                    sanitized_pages = [sanitize_data_for_xml(page) for page in pages]
                    build_multipage_docx(template_path, temporary_word, sanitized_pages)
                else:
                    replace_placeholders_in_file(template_path, temporary_word, document_data)
                unresolved = _unresolved_placeholders(temporary_word)
                if unresolved:
                    return _json_error('Generated DOCX contains unresolved placeholders', 500)
                success, converter, error = convert_to_pdf(temporary_word, temporary_pdf)
                if not success or not os.path.isfile(temporary_pdf):
                    print(f'[ERROR] PDF conversion failed: {error or "unknown error"}')
                    return _json_error('PDF conversion failed', 503)
                metadata = {
                    'pdfId': pdf_id,
                    'status': 'ready',
                    'workflow': workflow,
                    'worksheetNo': worksheet_no,
                    'filename': f'{worksheet_no}.pdf',
                    'templateHash': template_hash,
                    'templateOwner': PDF_WORKFLOW_REGISTRY[workflow]['owner'],
                    'templateFamily': PDF_WORKFLOW_REGISTRY[workflow]['family'],
                    'sourceWorkflow': PDF_WORKFLOW_REGISTRY[workflow].get('sourceWorkflow'),
                    'converter': converter,
                    'regeneratedAt': datetime.now().astimezone().isoformat() if existing_ids else None,
                    'supersededPdfIds': existing_ids if existing_ids else [],
                    'rendererVersion': DOCX_RENDERER_VERSION,
                    'fieldHashes': _field_hashes(document_data),
                    'changedFields': changed_fields,
                    'wordSha256': _hash_file(temporary_word),
                    'pdfSha256': _hash_file(temporary_pdf),
                    'wordSize': os.path.getsize(temporary_word),
                    'pdfSize': os.path.getsize(temporary_pdf),
                }
                with open(temporary_metadata, 'w', encoding='utf-8') as target:
                    json.dump(metadata, target, ensure_ascii=False, sort_keys=True)
                # Publish only after all three temporary files are complete. The
                # publish transaction stages and verifies every byte on the Share,
                # and leaves the previous worksheet version usable on failure.
                backup = _backup_artifacts(
                    workflow, worksheet_no, pdf_id,
                    temporary_word, temporary_pdf, temporary_metadata
                )
                if backup.get('status') != 'succeeded':
                    return _json_error(
                        backup.get('error') or 'Project share is unavailable; the worksheet was not saved',
                        503
                    )
                return jsonify({'pdfId': pdf_id, 'status': 'ready', 'cached': False, 'backup': backup}), 201
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                print(f'[ERROR] PDF generation failed: {error}')
                return _json_error('PDF generation failed', 500)
            finally:
                shutil.rmtree(temporary_dir, ignore_errors=True)


@app.route('/api/pdfs/<pdf_id>', methods=['GET'])
def get_pdf(pdf_id):
    metadata, pdf_path = _load_pdf_metadata(pdf_id)
    if not metadata:
        return _json_error('PDF not found', 404)
    return jsonify({
        'pdfId': metadata['pdfId'],
        'status': metadata['status'],
        'workflow': metadata['workflow'],
        'filename': metadata['filename']
    })


@app.route('/api/pdfs/<pdf_id>/backup-retry', methods=['POST'])
def retry_pdf_backup(pdf_id):
    metadata, pdf_path = _load_pdf_metadata(pdf_id)
    if not metadata:
        return _json_error('PDF not found', 404)
    # Controlled artifacts are published as one Share transaction. There is
    # intentionally no local spool to retry: a failed request never creates a
    # worksheet that exists only on this PC.
    return jsonify({
        'status': 'succeeded',
        'configured': True,
        'pdfId': pdf_id,
        'storage': 'project-share'
    })


@app.route('/api/backups/retry', methods=['POST'])
def retry_pending_backups():
    return jsonify({
        'status': 'complete',
        'configured': bool(PROJECT_SHARE_ROOT),
        'retried': [],
        'storage': 'project-share'
    })


@app.route('/api/pdfs/<pdf_id>/download', methods=['GET'])
def download_pdf(pdf_id):
    metadata, pdf_path = _load_pdf_metadata(pdf_id)
    if not metadata:
        return _json_error('PDF not found', 404)
    inline = request.args.get('inline') == '1'
    return send_file(pdf_path, mimetype='application/pdf', as_attachment=not inline,
                     download_name=metadata['filename'], conditional=True)


@app.route('/api/pdfs/<pdf_id>/save-desktop', methods=['POST'])
def save_pdf_to_desktop(pdf_id):
    return _json_error('Desktop saving is disabled; controlled files are saved to the project share', 410)

# --- who used the workspace, and who printed what ---------------------------
# QA asked "who printed this" and "who used this app". Both are answered here.
# The browser supplies only the operator's own employee number and what they
# did; the timestamp and the host come from this server, so they cannot be set
# from the page. See server/activity_log.py for what this is and is not.
@app.route('/api/log', methods=['POST'])
def write_activity_log():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error('A JSON object is required', 400)
    entry, reason = activity_log.record(
        action=str(payload.get('action') or ''),
        operator=payload.get('operator') or '',
        operator_name=payload.get('operatorName') or '',
        operator_code=payload.get('operatorCode') or '',
        worksheet_no=payload.get('worksheetNo') or '',
        detail=payload.get('detail') or '',
    )
    if entry is None:
        if reason == 'UNKNOWN_ACTION':
            return _json_error(f"Unknown log action; accepted actions are: {', '.join(sorted(activity_log.ACTIONS))}", 400)
        if reason == 'SHARE_UNAVAILABLE':
            return _json_error('Activity logging is disabled because the project share is not available', 503)
        return _json_error('Activity log write failed', 500)
    return jsonify({'ok': True, 'at': entry['at']})


@app.route('/api/log', methods=['GET'])
def read_activity_log():
    try:
        limit = min(2000, max(1, int(request.args.get('limit', 300))))
    except ValueError:
        limit = 300
    return jsonify({
        'ok': True,
        'entries': activity_log.read(limit),
        'forwarding': activity_log.forwarding_enabled(),
    })


@app.route('/api/log.csv', methods=['GET'])
def export_activity_log():
    stamp = datetime.now().strftime('%Y%m%d')
    return Response(
        activity_log.as_csv(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="anf3-activity-log-{stamp}.csv"'},
    )


@app.route('/api/status', methods=['GET'])
def status():
    """Check server status. Re-detect converters only when forced (?redetect=1)."""
    global MS_OFFICE_AVAILABLE, LIBREOFFICE_PATH

    if request.args.get('redetect') == '1':
        MS_OFFICE_AVAILABLE = find_msoffice()
        LIBREOFFICE_PATH = find_libreoffice()

    converter_available = MS_OFFICE_AVAILABLE or (LIBREOFFICE_PATH is not None)
    converter_name = (
        'Microsoft Office' if MS_OFFICE_AVAILABLE
        else ('LibreOffice' if LIBREOFFICE_PATH else None)
    )

    return jsonify({
        'status': 'running',
        'msOffice': MS_OFFICE_AVAILABLE,
        'libreOffice': LIBREOFFICE_PATH is not None,
        'converterAvailable': converter_available,
        'converterName': converter_name,
        'projectShareConfigured': bool(PROJECT_SHARE_ROOT),
        'projectShareAvailable': bool(PROJECT_SHARE_ROOT and os.path.isdir(PROJECT_SHARE_ROOT)),
        'projectSharePath': os.path.abspath(PROJECT_SHARE_ROOT) if PROJECT_SHARE_ROOT else None,
        'controlledStorage': 'project-share',
        'folders': FORM_FOLDERS
    })

@app.route('/api/check-pdf', methods=['GET'])
def check_pdf():
    return _json_error('Legacy PDF API removed; use /api/pdfs', 410)
    """Check if PDF already exists (for caching). Returns pages list for multi-page docs."""
    worksheet_no = request.args.get('worksheetNo', '')
    form_type = request.args.get('formType', 'pw-prw')

    if not worksheet_no:
        return jsonify({'exists': False, 'error': 'worksheetNo required'})

    pdf_folder = os.path.join(PDFS_DIR, form_type)

    # Check multi-page first: worksheetNo_p1.pdf, worksheetNo_p2.pdf, ...
    pages = []
    page = 1
    while True:
        p = os.path.join(pdf_folder, f'{worksheet_no}_p{page}.pdf')
        if os.path.exists(p):
            pages.append(f'{worksheet_no}_p{page}')
            page += 1
        else:
            break

    if pages:
        return jsonify({'exists': True, 'worksheetNo': worksheet_no, 'formType': form_type, 'pages': pages})

    # Fallback: single file
    single = os.path.join(pdf_folder, f'{worksheet_no}.pdf')
    if os.path.exists(single):
        return jsonify({'exists': True, 'worksheetNo': worksheet_no, 'formType': form_type, 'pages': [worksheet_no]})

    return jsonify({'exists': False, 'worksheetNo': worksheet_no, 'formType': form_type, 'pages': []})

@app.route('/api/get-cached-pdf', methods=['GET'])
def get_cached_pdf():
    return _json_error('Legacy PDF API removed; use a pdfId download URL', 410)
    """Get existing PDF file (cached)"""
    worksheet_no = request.args.get('worksheetNo', '')
    form_type = request.args.get('formType', 'pw-prw')
    
    if not worksheet_no:
        return jsonify({'error': 'worksheetNo required'}), 400
    
    pdf_folder = os.path.join(PDFS_DIR, form_type)
    pdf_path = os.path.join(pdf_folder, f'{worksheet_no}.pdf')
    
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'PDF not found'}), 404
    
    print(f"[CACHE] Returning cached PDF: {pdf_path}")
    return send_file(pdf_path, mimetype='application/pdf')

@app.route('/api/generate-words', methods=['POST'])
def generate_words():
    return _json_error('Legacy PDF API removed; use /api/pdfs', 410)
    """Step 1: สร้าง DOCX ทุกไฟล์ก่อน คืน list ของ fileKeys ที่พร้อม convert"""
    try:
        data = request.json
        template_name = data.get('templateName', 'pw-prw-template.docx')
        form_type     = data.get('formType', get_form_folder(template_name))
        pages         = data.get('pages', [])  # [{worksheetNo, tags}]

        template_path = os.path.join(TEMPLATE_DIR, template_name)
        if not os.path.exists(template_path):
            return jsonify({'error': f'Template not found: {template_name}'}), 500

        word_folder = os.path.join(WORDS_DIR, form_type)
        os.makedirs(word_folder, exist_ok=True)

        created = []
        for p in pages:
            key       = p.get('worksheetNo')
            tags      = p.get('tags', {})
            word_path = os.path.join(word_folder, f'{key}.docx')
            replace_placeholders_in_file(template_path, word_path, tags)
            created.append({'key': key, 'wordPath': word_path})
            print(f"[WORD] created: {word_path}")

        return jsonify({'success': True, 'files': created})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/convert-word-to-pdf', methods=['POST'])
def convert_word_to_pdf():
    return _json_error('Legacy path-based API removed; use /api/pdfs', 410)
    """Step 2: รับ wordPath เดียว แปลง PDF แล้วคืน PDF blob"""
    try:
        data      = request.json
        word_path = data.get('wordPath')
        form_type = data.get('formType', 'pw-prw')
        key       = data.get('key')

        if not word_path or not os.path.exists(word_path):
            return jsonify({'error': f'Word file not found: {word_path}'}), 404

        pdf_folder = os.path.join(PDFS_DIR, form_type)
        os.makedirs(pdf_folder, exist_ok=True)
        pdf_path = os.path.join(pdf_folder, f'{key}.pdf')

        success, converter, error = convert_to_pdf(word_path, pdf_path)
        if not success:
            return jsonify({'error': error or 'PDF conversion failed'}), 500
        if not os.path.exists(pdf_path):
            return jsonify({'error': 'PDF file not created'}), 500

        return send_file(pdf_path, mimetype='application/pdf')
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/preview-pdf', methods=['POST'])
def preview_pdf():
    return _json_error('Legacy PDF API removed; use /api/pdfs', 410)
    """Generate Word + Convert to PDF + Return PDF.
    Accepts either:
      - legacy: { worksheetNo, templateName, formType, ...tags }
      - multi-page: { worksheetNo, templateName, formType, pages: [{...tags}, ...] }
    """
    try:
        data = request.json
        worksheet_no = data.get('worksheetNo', 'preview')
        template_name = data.get('templateName', 'pw-prw-template.docx')
        form_type = data.get('formType', get_form_folder(template_name))
        pages_input = data.get('pages')   # list of per-page tag dicts, or None

        template_path = os.path.join(TEMPLATE_DIR, template_name)
        if not os.path.exists(template_path):
            return jsonify({'error': f'Template not found: {template_name}'}), 500

        word_folder = os.path.join(WORDS_DIR, form_type)
        pdf_folder  = os.path.join(PDFS_DIR,  form_type)
        os.makedirs(word_folder, exist_ok=True)
        os.makedirs(pdf_folder,  exist_ok=True)

        word_path = os.path.join(word_folder, f'{worksheet_no}.docx')
        pdf_path  = os.path.join(pdf_folder,  f'{worksheet_no}.pdf')

        print(f"\n[PDF] {worksheet_no} | {template_name} | pages={len(pages_input) if pages_input else 1}")

        if pages_input and len(pages_input) > 0:
            # Multi-page: sanitize each page's data and build single DOCX
            sanitized_pages = [sanitize_data_for_xml(p) for p in pages_input]
            build_multipage_docx(template_path, word_path, sanitized_pages)
        else:
            # Single page (legacy)
            replace_placeholders_in_file(template_path, word_path, data)

        success, converter, error = convert_to_pdf(word_path, pdf_path)
        if not success:
            detail = error or 'PDF conversion failed'
            if 'no pdf converter' in detail.lower() or 'not available' in detail.lower():
                detail = ('No PDF converter available. Install Microsoft Office + run '
                          'INSTALL-MSOFFICE-SUPPORT.bat, or install LibreOffice.')
            return jsonify({'error': detail}), 500

        if not os.path.exists(pdf_path):
            return jsonify({'error': 'PDF file not created'}), 500

        return send_file(pdf_path, mimetype='application/pdf')

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/print-pdf', methods=['POST'])
def print_pdf():
    return _json_error('Legacy PDF API removed; use /api/pdfs/<pdfId>/save-desktop', 410)
    """Copy PDF to Desktop"""
    try:
        data = request.json
        worksheet_no = data.get('worksheetNo')
        form_type = data.get('formType', 'pw-prw')
        copy_to_desktop = data.get('copyToDesktop', True)
        
        pdf_folder = os.path.join(PDFS_DIR, form_type)
        pdf_path = os.path.join(pdf_folder, f'{worksheet_no}.pdf')
        
        if not os.path.exists(pdf_path):
            # Try finding in base folder (backward compatibility)
            pdf_path_old = os.path.join(PDFS_DIR, f'{worksheet_no}.pdf')
            if os.path.exists(pdf_path_old):
                pdf_path = pdf_path_old
            else:
                return jsonify({'error': f'PDF not found'}), 404
        
        if copy_to_desktop:
            desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
            dest_path = os.path.join(desktop, f'{worksheet_no}.pdf')
            shutil.copy2(pdf_path, dest_path)
            
            return jsonify({
                'success': True,
                'path': dest_path,
                'filename': f'{worksheet_no}.pdf'
            })
        
        return jsonify({'success': True, 'path': pdf_path})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-desktop-files', methods=['POST'])
def check_desktop_files():
    return _json_error('Legacy path-based API removed', 410)
    """Check if Word/PDF files already exist on Desktop for given worksheetNo + pages"""
    try:
        data = request.json
        worksheet_no = data.get('worksheetNo', '')
        page_keys = data.get('pageKeys', [worksheet_no])  # list of keys e.g. ["AT-26-0026_p1","AT-26-0026_p2"]
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')

        existing = [k for k in page_keys if os.path.exists(os.path.join(desktop, f'{k}.pdf'))]
        return jsonify({'existing': existing})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/list-files', methods=['GET'])
def list_files():
    return _json_error('File listing is not available', 410)
    """List generated files"""
    try:
        files = {}
        
        for form_type in FORM_FOLDERS:
            word_folder = os.path.join(WORDS_DIR, form_type)
            pdf_folder = os.path.join(PDFS_DIR, form_type)
            
            files[form_type] = {
                'words': os.listdir(word_folder) if os.path.exists(word_folder) else [],
                'pdfs': os.listdir(pdf_folder) if os.path.exists(pdf_folder) else []
            }
        
        return jsonify(files)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# Main
# ============================================

if __name__ == '__main__':
    import webbrowser
    import threading
    import logging
    
    # Suppress Flask logs
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    print()
    print("=" * 60)
    print("   WATER RECORD SYSTEM - PDF SERVER v4.2.0")
    print("=" * 60)
    print()
    print("   Folder Structure:")
    print(f"   Words: {WORDS_DIR}")
    print(f"   PDFs:  {PDFS_DIR}")
    print()
    print("   Supported Form Types:")
    for folder in FORM_FOLDERS:
        print(f"   - {folder}")
    print()
    
    if MS_OFFICE_AVAILABLE:
        print("   [OK] PDF Converter: Microsoft Office")
    elif LIBREOFFICE_PATH:
        print("   [OK] PDF Converter: LibreOffice")
        print(f"        Path: {LIBREOFFICE_PATH}")
    else:
        print("   [!!] PDF Converter: NOT FOUND")
        print()
        print("   To enable PDF generation, install one of:")
        print("   1. Microsoft Office + pywin32")
        print("      Run: INSTALL-MSOFFICE-SUPPORT.bat")
        print("   2. LibreOffice (free)")
        print("      https://www.libreoffice.org/download/")
    
    print()
    print("=" * 60)
    print("   SERVER IS RUNNING!")
    print("=" * 60)
    print()
    host = os.environ.get('ANF3_HOST', '127.0.0.1')
    try:
        preferred = int(os.environ.get('ANF3_PORT', '8000'))
    except ValueError:
        preferred = 8000
    port = _pick_free_port(host, preferred)
    _write_port_file(port)

    url = f"http://localhost:{port}"
    print(f"   URL: {url}")
    if port != preferred:
        print()
        print(f"   [i] Port {preferred} was busy, so this session uses {port}.")
        print("       Another program is already using the usual port; nothing is wrong.")
    print()
    print("   [!] Keep this window open while using the app")
    print("   [!] Press Ctrl+C to stop the server")
    print()
    print("=" * 60)
    print()

    if not os.environ.get('ANF3_NO_BROWSER'):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        app.run(host=host, port=port, debug=False)
    finally:
        _clear_port_file()
