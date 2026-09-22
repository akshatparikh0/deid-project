from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pymupdf
from pypdf import PdfReader


MAX_PDF_SIZE = 50 * 1024 * 1024
MAX_PAGE_COUNT = 500


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    size_bytes: int
    page_count: int
    encrypted: bool
    has_metadata: bool
    sha256: str


def _read_pdf_bytes(file_obj: BinaryIO) -> bytes:
    """Read an uploaded/local file without permanently moving its cursor."""
    original_position = None

    try:
        original_position = file_obj.tell()
    except (AttributeError, OSError):
        pass

    try:
        file_obj.seek(0)
        data = file_obj.read()
    finally:
        if original_position is not None:
            file_obj.seek(original_position)

    return data


def validate_pdf(
    file_obj: BinaryIO,
    *,
    filename: str | None = None,
    max_size_bytes: int = MAX_PDF_SIZE,
    max_page_count: int = MAX_PAGE_COUNT,
) -> ValidationResult:
    resolved_name = filename or getattr(file_obj, "name", "")

    if resolved_name and Path(resolved_name).suffix.lower() != ".pdf":
        raise ValidationError("Only PDF files are supported.")

    data = _read_pdf_bytes(file_obj)
    size = len(data)

    if size == 0:
        raise ValidationError("The uploaded PDF is empty.")

    if size > max_size_bytes:
        raise ValidationError(
            f"The PDF exceeds the {max_size_bytes // (1024 * 1024)} MB limit."
        )

    if not data.startswith(b"%PDF-"):
        raise ValidationError(
            "The uploaded file does not have a valid PDF signature."
        )

    try:
        reader = PdfReader(io.BytesIO(data), strict=True)

        if reader.is_encrypted:
            raise ValidationError(
                "Password-protected or encrypted PDFs are not accepted."
            )

        pypdf_page_count = len(reader.pages)

        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ValidationError(
                    "Password-protected or encrypted PDFs are not accepted."
                )

            pymupdf_page_count = pdf.page_count
            has_metadata = any((pdf.metadata or {}).values())

    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(
            f"The PDF is unreadable or corrupt: {exc}"
        ) from exc

    if pypdf_page_count < 1:
        raise ValidationError("The PDF has no pages.")

    if pypdf_page_count != pymupdf_page_count:
        raise ValidationError(
            "The PDF parsers disagree about the number of pages."
        )

    if pypdf_page_count > max_page_count:
        raise ValidationError(
            f"The PDF exceeds the {max_page_count}-page limit."
        )

    return ValidationResult(
        size_bytes=size,
        page_count=pypdf_page_count,
        encrypted=False,
        has_metadata=has_metadata,
        sha256=hashlib.sha256(data).hexdigest(),
    )