from pathlib import Path

from src.domain.models import ApiUsage, ExtractedBlock, JobStatus, PdfChunk
from src.repositories.checkpoint_repository import SqlCheckpointRepository


def test_repository_recovers_completed_block(tmp_path: Path) -> None:
    repository = SqlCheckpointRepository(f"sqlite:///{tmp_path / 'test.db'}")
    chunk = PdfChunk(0, 1, 4, b"pdf", "a" * 64)
    job = repository.get_or_create_job(
        user_id="user-1",
        pdf_hash="b" * 64,
        filename="presupuesto.pdf",
        model="gpt-5.6-luna",
        detail="high",
        schema_version="v1",
        total_blocks=1,
    )
    repository.mark_block_processing(job.job_id, chunk)
    block = ExtractedBlock(conceptos=[], advertencias=[])
    repository.save_block_success(job.job_id, chunk, block, ApiUsage(10, 5, "req-1"))
    repository.set_job_status(job.job_id, JobStatus.COMPLETED)

    cached = repository.get_completed_block(job.job_id, chunk)
    assert cached is not None
    assert cached[1].input_tokens == 10
    assert repository.list_jobs("user-1")[0].completed_blocks == 1
    baseline = repository.get_usage_baseline(
        user_id="user-1",
        model="gpt-5.6-luna",
        detail="high",
        schema_version="v1",
    )
    assert baseline is not None
    assert baseline.sample_blocks == 1
    assert baseline.input_tokens_per_block == 10
    assert baseline.output_tokens_per_block == 5
