"""Central resource limits and safe display metadata."""

import unicodedata

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 30
MAX_ARCHIVE_ENTRIES = 256
MAX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_PART_BYTES = 8 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_BLOCKS = 2000
MAX_TEXT_CHARACTERS = 200_000
MIN_TEXT_CHARACTERS = 20
MAX_EVENTS = 32
SUPPORTED_TYPES = ("pdf", "docx")


def display_filename(name: object) -> str:
    """A plain display label, never a filesystem path or Markdown fragment."""
    if not isinstance(name, str):
        return "未命名文件"
    base = name.replace("\\", "/").split("/")[-1]
    base = "".join(char for char in base if not unicodedata.category(char).startswith("C"))
    base = base.translate(str.maketrans({char: "_" for char in '<>"`*[]{}'})).strip(" .")
    if len(base) > 120:
        stem, dot, suffix = base.rpartition(".")
        base = stem[:100] + dot + suffix[:16] if dot else base[:120]
    return base or "未命名文件"


def file_type(name: object) -> str:
    label = display_filename(name)
    suffix = label.rpartition(".")[2].casefold() if "." in label else ""
    return suffix if suffix in SUPPORTED_TYPES else "unknown"
