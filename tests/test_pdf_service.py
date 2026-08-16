from io import BytesIO

from pypdf import PdfWriter

from src.services.pdf_service import PdfChunker


def make_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_chunker_uses_overlap_without_losing_pages() -> None:
    chunks = PdfChunker(chunk_size=4, overlap=1).split(make_pdf(10))
    assert [(chunk.page_start, chunk.page_end) for chunk in chunks] == [
        (1, 4),
        (4, 7),
        (7, 10),
    ]
    assert all(len(chunk.sha256) == 64 for chunk in chunks)


def test_file_hash_is_stable() -> None:
    pdf = make_pdf(2)
    assert PdfChunker.file_hash(pdf) == PdfChunker.file_hash(pdf)

