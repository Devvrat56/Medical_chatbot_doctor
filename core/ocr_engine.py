# core/ocr_engine.py — FINAL WINDOWS-SAFE VERSION (NO POPPLER, NO PERMISSION ERRORS)

from pathlib import Path
from typing import Union
import os
import tempfile

import easyocr
import fitz  # PyMuPDF


_reader = None


def _get_reader(langs=None, gpu=False):
    global _reader
    if _reader is None:
        langs = langs or ["en"]
        _reader = easyocr.Reader(langs, gpu=gpu)
    return _reader


def ocr_image(path: Union[str, Path], langs=None, gpu=False) -> str:
    """OCR image using EasyOCR."""
    try:
        reader = _get_reader(langs, gpu)
        result = reader.readtext(str(path), detail=0, paragraph=True)
        return "\n".join(result)
    except Exception as e:
        return f"⚠️ Image OCR failed: {e}"


def ocr_pdf_pymupdf(path: Union[str, Path], langs=None, gpu=False, zoom=2.0) -> str:
    """
    OCR PDF using PyMuPDF (fitz) → convert each page to image.
    Uses Windows-safe manual temp file creation.
    """
    texts = []

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        return f"⚠️ Failed to open PDF: {e}"

    temp_dir = tempfile.gettempdir()

    for page_number in range(len(doc)):
        try:
            page = doc.load_page(page_number)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Windows-safe temp file creation
            temp_path = os.path.join(temp_dir, f"pdf_page_{os.getpid()}_{page_number}.png")
            pix.save(temp_path)

            # OCR page
            text = ocr_image(temp_path, langs, gpu)
            texts.append(f"--- PAGE {page_number + 1} ---\n{text}")

        except Exception as e:
            texts.append(f"⚠️ Failed OCR on page {page_number + 1}: {e}")

        finally:
            # Always try delete without raising exceptions
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass

    return "\n\n".join(texts)


def extract_text_from_file(path: Union[str, Path], langs=None, gpu=False) -> str:
    """Autodetect file type."""
    suffix = Path(path).suffix.lower()

    if suffix == ".pdf":
        return ocr_pdf_pymupdf(path, langs, gpu)

    return ocr_image(path, langs, gpu)
