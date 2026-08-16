"""Lectura y división segura de PDFs sin realizar OCR local."""

from __future__ import annotations

import hashlib
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from src.domain.models import PdfChunk


class PdfProcessingError(ValueError):
    pass


class PdfChunker:
    def __init__(self, chunk_size: int = 4, overlap: int = 1) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size debe ser mayor que cero.")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap debe estar entre 0 y chunk_size - 1.")
        self._chunk_size = chunk_size
        self._overlap = overlap

    @staticmethod
    def file_hash(pdf_bytes: bytes) -> str:
        return hashlib.sha256(pdf_bytes).hexdigest()

    def split(self, pdf_bytes: bytes) -> list[PdfChunk]:
        if not pdf_bytes.startswith(b"%PDF"):
            raise PdfProcessingError("El archivo cargado no parece ser un PDF válido.")
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
        except Exception as exc:
            raise PdfProcessingError("No fue posible abrir el PDF.") from exc
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:
                raise PdfProcessingError("El PDF está protegido con contraseña.") from exc
            if not unlocked:
                raise PdfProcessingError("El PDF está protegido con contraseña.")
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise PdfProcessingError("El PDF no contiene páginas.")

        chunks: list[PdfChunk] = []
        start = 0
        index = 0
        step = self._chunk_size - self._overlap
        while start < total_pages:
            end = min(start + self._chunk_size, total_pages)
            writer = PdfWriter()
            for page_index in range(start, end):
                writer.add_page(reader.pages[page_index])
            buffer = BytesIO()
            writer.write(buffer)
            content = buffer.getvalue()
            chunks.append(
                PdfChunk(
                    index=index,
                    page_start=start + 1,
                    page_end=end,
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                )
            )
            if end == total_pages:
                break
            start += step
            index += 1
        return chunks

