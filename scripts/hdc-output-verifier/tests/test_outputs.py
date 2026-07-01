"""Custom tests for validating generated document files pulled from the device."""

import os
import re
import zipfile

import pytest
from html.parser import HTMLParser

TEST_MODE = os.environ.get("TEST_MODE", "test1").lower()
EXPECTED_FILE = os.environ.get("EXPECTED_FILE", "finance.html")
EXPECTED_FILES = [f.strip() for f in os.environ.get("EXPECTED_FILES", EXPECTED_FILE).split(",") if f.strip()]
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")

MIN_SIZE_BY_EXT = {
    ".html": 200,
    ".htm": 200,
    ".md": 100,
    ".markdown": 100,
    ".pdf": 500,
    ".docx": 1000,
    ".pptx": 1000,
}
TEST1_EXTENSIONS = {".html", ".htm"}
TEST2_EXTENSIONS = {".pdf", ".pptx", ".docx", ".md", ".markdown"}
FINANCE_KEYWORDS = ["finance", "stock", "market", "a股", "股票", "证券", "指数", "交易", "行情", "板块"]
FAILURE_TERMS = ["error", "exception", "traceback", "无法生成", "生成失败", "出错", "抱歉"]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.text_parts.append(data.strip())


def _path(file_name: str) -> str:
    return os.path.join(OUTPUT_DIR, file_name)


def _ext(file_name: str) -> str:
    return os.path.splitext(file_name.lower())[1]


def _basename_without_ext(file_name: str) -> str:
    return os.path.splitext(os.path.basename(file_name))[0]


def _read_text(file_name: str) -> str:
    with open(_path(file_name), encoding="utf-8", errors="ignore") as f:
        return f.read()


def _read_bytes(file_name: str) -> bytes:
    with open(_path(file_name), "rb") as f:
        return f.read()


def _zip_names(file_name: str):
    with zipfile.ZipFile(_path(file_name)) as zf:
        return set(zf.namelist())


def _zip_text_entries(file_name: str, *suffixes) -> str:
    texts = []
    with zipfile.ZipFile(_path(file_name)) as zf:
        for name in zf.namelist():
            if suffixes and not name.endswith(suffixes):
                continue
            texts.append(zf.read(name).decode("utf-8", errors="ignore"))
    return "\n".join(texts)


def _text_for_keyword_checks(file_name: str) -> str:
    ext = _ext(file_name)
    if ext in (".html", ".htm", ".md", ".markdown"):
        return _read_text(file_name)
    if ext == ".docx":
        return _zip_text_entries(file_name, "word/document.xml")
    if ext == ".pptx":
        texts = []
        with zipfile.ZipFile(_path(file_name)) as zf:
            for name in zf.namelist():
                if re.match(r"ppt/slides/slide\d+\.xml$", name):
                    texts.append(zf.read(name).decode("utf-8", errors="ignore"))
        return "\n".join(texts)
    return ""


def _expected_extensions_for_mode():
    if TEST_MODE == "test1":
        return TEST1_EXTENSIONS
    if TEST_MODE == "test2":
        return TEST2_EXTENSIONS
    raise AssertionError(f"Unsupported TEST_MODE: {TEST_MODE}. Use test1 or test2")


def _expected_files_for_mode():
    if TEST_MODE == "test1":
        return EXPECTED_FILES

    # test2 validates a conversion task that must produce all four formats.
    base = _basename_without_ext(EXPECTED_FILES[0] if EXPECTED_FILES else EXPECTED_FILE)
    return [f"{base}.pdf", f"{base}.pptx", f"{base}.docx", f"{base}.md"]


def _assert_file_signature(file_name: str):
    ext = _ext(file_name)
    data = _read_bytes(file_name)[:16]
    if ext in (".html", ".htm"):
        text = _read_text(file_name).lower()
        assert "<html" in text and "<body" in text, "HTML should contain <html> and <body> tags"
    elif ext in (".md", ".markdown"):
        text = _read_text(file_name)
        assert not text.lstrip().startswith("<html"), "Markdown output should not be raw HTML"
        assert re.search(r"(^#\s+|\n#\s+|^[-*]\s+|\n[-*]\s+|\|.+\|)", text), "Markdown should contain heading/list/table syntax"
    elif ext == ".pdf":
        assert data.startswith(b"%PDF-"), "PDF should start with %PDF- signature"
    elif ext in (".docx", ".pptx"):
        assert data.startswith(b"PK"), f"{ext} should be a ZIP/OpenXML container"
        assert zipfile.is_zipfile(_path(file_name)), f"{ext} should be a valid ZIP/OpenXML file"


def _assert_office_structure(file_name: str):
    ext = _ext(file_name)
    if ext not in (".docx", ".pptx"):
        return
    names = _zip_names(file_name)
    assert "[Content_Types].xml" in names, "OpenXML package missing [Content_Types].xml"
    assert any(name.startswith("_rels/") for name in names), "OpenXML package missing relationships"
    if ext == ".docx":
        assert "word/document.xml" in names, "DOCX missing word/document.xml"
    if ext == ".pptx":
        assert "ppt/presentation.xml" in names, "PPTX missing ppt/presentation.xml"
        slide_names = [name for name in names if re.match(r"ppt/slides/slide\d+\.xml$", name)]
        assert slide_names, "PPTX should contain at least one slide XML"


def test_expected_file_set_matches_mode():
    files = _expected_files_for_mode()
    exts = {_ext(file) for file in files}
    allowed = _expected_extensions_for_mode()
    assert exts <= allowed, f"{TEST_MODE} got unsupported extensions: {exts - allowed}"
    if TEST_MODE == "test2":
        assert exts == {".pdf", ".pptx", ".docx", ".md"}, f"test2 must validate pdf/pptx/docx/md; got {exts}"


@pytest.mark.parametrize("file_name", _expected_files_for_mode())
def test_generated_file_exists(file_name):
    assert os.path.exists(_path(file_name)), f"Expected generated file not found: {_path(file_name)}"


@pytest.mark.parametrize("file_name", _expected_files_for_mode())
def test_generated_file_not_empty(file_name):
    ext = _ext(file_name)
    size = os.path.getsize(_path(file_name))
    min_size = MIN_SIZE_BY_EXT[ext]
    assert size >= min_size, f"Generated {ext} file is too small: {size} bytes, expected >= {min_size}"


@pytest.mark.parametrize("file_name", _expected_files_for_mode())
def test_generated_file_format_signature(file_name):
    _assert_file_signature(file_name)


@pytest.mark.parametrize("file_name", _expected_files_for_mode())
def test_generated_office_container_structure(file_name):
    _assert_office_structure(file_name)


@pytest.mark.parametrize("file_name", _expected_files_for_mode())
def test_generated_content_mentions_finance_topic_when_text_extractable(file_name):
    if _ext(file_name) == ".pdf":
        return
    text = _text_for_keyword_checks(file_name).lower()
    matched = [kw for kw in FINANCE_KEYWORDS if kw in text]
    assert matched, f"Expected finance or market-related keywords in generated {file_name}"


@pytest.mark.parametrize("file_name", _expected_files_for_mode())
def test_generated_text_format_has_sections(file_name):
    ext = _ext(file_name)
    if ext in (".html", ".htm"):
        html = _read_text(file_name).lower()
        has_title_or_heading = re.search(r"<title[^>]*>.+?</title>", html, re.S) or re.search(r"<h[1-3][^>]*>.+?</h[1-3]>", html, re.S)
        markers = len(re.findall(r"<h[1-6]\b|<section\b|<article\b|<table\b|<ul\b|<ol\b", html))
        assert has_title_or_heading or markers >= 1, "Expected a <title>, heading, or section/list/table marker"
    elif ext in (".md", ".markdown"):
        text = _read_text(file_name)
        headings = re.findall(r"^#{1,6}\s+", text, re.M)
        lists_or_tables = re.findall(r"^[-*]\s+|^\|.+\|", text, re.M)
        assert headings or lists_or_tables, "Markdown should contain at least one heading, list, or table marker"


@pytest.mark.parametrize("file_name", _expected_files_for_mode())
def test_generated_file_has_no_obvious_failure_text_when_text_extractable(file_name):
    if _ext(file_name) == ".pdf":
        return
    text = _text_for_keyword_checks(file_name).lower()
    found = [term for term in FAILURE_TERMS if term in text]
    assert not found, f"Generated {file_name} appears to contain failure text: {found}"
