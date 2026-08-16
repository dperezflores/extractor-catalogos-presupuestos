from io import BytesIO

from pypdf import PdfWriter

from src.config import AppSettings
from src.domain.models import ApiUsage, ExtractedBlock, UserIdentity
from src.repositories.checkpoint_repository import SqlCheckpointRepository
from src.services.pdf_service import PdfChunker
from src.services.processing_service import CatalogProcessingService
from src.services.validation_service import CatalogValidator


def make_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_preview_reports_only_blocks_missing_from_cache(tmp_path) -> None:
    settings = AppSettings(chunk_size=4, chunk_overlap=1)
    repository = SqlCheckpointRepository(f"sqlite:///{tmp_path / 'preview.db'}")
    chunker = PdfChunker(settings.chunk_size, settings.chunk_overlap)
    service = CatalogProcessingService(
        settings=settings,
        repository=repository,
        chunker=chunker,
        validator=CatalogValidator(),
    )
    user = UserIdentity("user-1", "Usuario", "usuario@example.com")
    pdf = make_pdf(5)

    initial = service.preview(user=user, pdf_bytes=pdf, filename="presupuesto.pdf")
    assert initial.total_pages == 5
    assert initial.total_blocks == 2
    assert initial.cached_blocks == 0
    assert initial.pending_blocks == 2
    assert initial.estimate_sample_blocks == 0

    job = repository.get_or_create_job(
        user_id=user.user_id,
        pdf_hash=chunker.file_hash(pdf),
        filename="presupuesto.pdf",
        model=settings.model,
        detail=settings.pdf_detail,
        schema_version="catalog-v1-c4-o1",
        total_blocks=2,
    )
    first_chunk = chunker.split(pdf)[0]
    repository.mark_block_processing(job.job_id, first_chunk)
    repository.save_block_success(
        job.job_id,
        first_chunk,
        ExtractedBlock(conceptos=[], advertencias=[]),
        ApiUsage(100, 20, "req-1"),
    )

    resumed = service.preview(user=user, pdf_bytes=pdf, filename="presupuesto.pdf")
    assert resumed.cached_blocks == 1
    assert resumed.pending_blocks == 1
    assert resumed.estimated_input_tokens == 100
    assert resumed.estimated_output_tokens == 20
    assert resumed.estimated_cost_usd == 0.000044
    assert resumed.estimate_sample_blocks == 1


def test_cost_estimate_matches_document_usage(tmp_path) -> None:
    settings = AppSettings()
    service = CatalogProcessingService(
        settings=settings,
        repository=SqlCheckpointRepository(f"sqlite:///{tmp_path / 'cost.db'}"),
        chunker=PdfChunker(settings.chunk_size, settings.chunk_overlap),
        validator=CatalogValidator(),
    )

    assert service._calculate_cost(ApiUsage(590_413, 271_282)) == 0.443621
