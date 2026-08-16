"""Caso de uso principal: extraer, reanudar, validar y consolidar el catálogo."""

from __future__ import annotations

from src.config import AppSettings
from src.domain.models import (
    ApiUsage,
    ExtractedConcept,
    JobStatus,
    ProcessingResult,
    ProgressCallback,
    UserIdentity,
)
from src.repositories.checkpoint_repository import CheckpointRepository
from src.services.openai_extractor import OpenAICatalogExtractor
from src.services.pdf_service import PdfChunker
from src.services.validation_service import CatalogValidator


class CatalogProcessingService:
    def __init__(
        self,
        settings: AppSettings,
        repository: CheckpointRepository,
        chunker: PdfChunker,
        validator: CatalogValidator,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._chunker = chunker
        self._validator = validator

    def validate_api_key(self, api_key: str) -> None:
        self._extractor(api_key).validate_credentials()

    def process(
        self,
        *,
        user: UserIdentity,
        api_key: str,
        pdf_bytes: bytes,
        filename: str,
        progress: ProgressCallback | None = None,
    ) -> ProcessingResult:
        chunks = self._chunker.split(pdf_bytes)
        pdf_hash = self._chunker.file_hash(pdf_bytes)
        cache_schema = (
            f"{self._settings.schema_version}"
            f"-c{self._settings.chunk_size}"
            f"-o{self._settings.chunk_overlap}"
        )
        job = self._repository.get_or_create_job(
            user_id=user.user_id,
            pdf_hash=pdf_hash,
            filename=filename,
            model=self._settings.model,
            detail=self._settings.pdf_detail,
            schema_version=cache_schema,
            total_blocks=len(chunks),
        )
        extractor = self._extractor(api_key)
        concepts: list[ExtractedConcept] = []
        total_usage = ApiUsage()
        cached_blocks = 0
        processed_blocks = 0

        for position, chunk in enumerate(chunks, start=1):
            cached = self._repository.get_completed_block(job.job_id, chunk)
            if cached is not None:
                block, usage = cached
                concepts.extend(block.conceptos)
                total_usage += usage
                cached_blocks += 1
                if progress:
                    progress(position, len(chunks), f"Bloque {position} recuperado")
                continue

            self._repository.mark_block_processing(job.job_id, chunk)
            if progress:
                progress(
                    position - 1,
                    len(chunks),
                    f"Leyendo páginas {chunk.page_start}–{chunk.page_end}",
                )
            try:
                result = extractor.extract(chunk)
                self._repository.save_block_success(
                    job.job_id, chunk, result.block, result.usage
                )
            except Exception as exc:
                self._repository.save_block_error(job.job_id, chunk, str(exc))
                raise
            concepts.extend(result.block.conceptos)
            total_usage += result.usage
            processed_blocks += 1
            if progress:
                progress(position, len(chunks), f"Bloque {position} guardado")

        catalog = self._validator.validate_and_merge(concepts)
        self._repository.set_job_status(job.job_id, JobStatus.COMPLETED)
        job.status = JobStatus.COMPLETED
        job.completed_blocks = len(chunks)
        return ProcessingResult(
            job=job,
            catalog=catalog,
            usage=total_usage,
            cached_blocks=cached_blocks,
            processed_blocks=processed_blocks,
        )

    def _extractor(self, api_key: str) -> OpenAICatalogExtractor:
        return OpenAICatalogExtractor(
            api_key=api_key,
            model=self._settings.model,
            detail=self._settings.pdf_detail,
            reasoning_effort=self._settings.reasoning_effort,
        )
