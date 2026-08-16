"""Persistencia de trabajos y checkpoints, compatible con SQLite y PostgreSQL."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from src.domain.models import (
    ApiUsage,
    BlockStatus,
    ExtractedBlock,
    JobRecord,
    JobStatus,
    PdfChunk,
    UsageBaseline,
)


class CheckpointRepository(ABC):
    @abstractmethod
    def get_or_create_job(
        self,
        *,
        user_id: str,
        pdf_hash: str,
        filename: str,
        model: str,
        detail: str,
        schema_version: str,
        total_blocks: int,
    ) -> JobRecord: ...

    @abstractmethod
    def get_completed_block(
        self, job_id: str, chunk: PdfChunk
    ) -> tuple[ExtractedBlock, ApiUsage] | None: ...

    @abstractmethod
    def mark_block_processing(self, job_id: str, chunk: PdfChunk) -> None: ...

    @abstractmethod
    def save_block_success(
        self,
        job_id: str,
        chunk: PdfChunk,
        result: ExtractedBlock,
        usage: ApiUsage,
    ) -> None: ...

    @abstractmethod
    def save_block_error(self, job_id: str, chunk: PdfChunk, error: str) -> None: ...

    @abstractmethod
    def set_job_status(self, job_id: str, status: JobStatus) -> None: ...

    @abstractmethod
    def list_jobs(self, user_id: str, limit: int = 50) -> list[JobRecord]: ...

    @abstractmethod
    def get_usage_baseline(
        self,
        *,
        user_id: str,
        model: str,
        detail: str,
        schema_version: str,
    ) -> UsageBaseline | None: ...


class SqlCheckpointRepository(CheckpointRepository):
    """Repositorio transaccional; usa una conexión por operación."""

    def __init__(self, database_url: str) -> None:
        self._database_url = self._normalize_url(database_url)
        self._engine = self._build_engine(self._database_url)
        self._metadata = MetaData()
        self._jobs = Table(
            "jobs",
            self._metadata,
            Column("job_id", String(36), primary_key=True),
            Column("user_id", String(255), nullable=False, index=True),
            Column("pdf_hash", String(64), nullable=False),
            Column("filename", String(512), nullable=False),
            Column("model", String(80), nullable=False),
            Column("detail", String(20), nullable=False),
            Column("schema_version", String(80), nullable=False),
            Column("status", String(40), nullable=False),
            Column("total_blocks", Integer, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            UniqueConstraint(
                "user_id",
                "pdf_hash",
                "model",
                "detail",
                "schema_version",
                name="uq_job_resume_key",
            ),
        )
        self._blocks = Table(
            "job_blocks",
            self._metadata,
            Column("job_id", String(36), primary_key=True),
            Column("block_index", Integer, primary_key=True),
            Column("page_start", Integer, nullable=False),
            Column("page_end", Integer, nullable=False),
            Column("chunk_hash", String(64), nullable=False),
            Column("status", String(40), nullable=False),
            Column("result_json", Text, nullable=True),
            Column("input_tokens", Integer, nullable=False, default=0),
            Column("output_tokens", Integer, nullable=False, default=0),
            Column("request_id", String(255), nullable=False, default=""),
            Column("error", Text, nullable=False, default=""),
            Column("attempts", Integer, nullable=False, default=0),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )
        self._metadata.create_all(self._engine)

    @staticmethod
    def _normalize_url(url: str) -> str:
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @staticmethod
    def _build_engine(url: str) -> Engine:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        return create_engine(url, pool_pre_ping=True, connect_args=connect_args)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def get_or_create_job(
        self,
        *,
        user_id: str,
        pdf_hash: str,
        filename: str,
        model: str,
        detail: str,
        schema_version: str,
        total_blocks: int,
    ) -> JobRecord:
        criteria = (
            (self._jobs.c.user_id == user_id)
            & (self._jobs.c.pdf_hash == pdf_hash)
            & (self._jobs.c.model == model)
            & (self._jobs.c.detail == detail)
            & (self._jobs.c.schema_version == schema_version)
        )
        with self._engine.begin() as connection:
            row = connection.execute(select(self._jobs).where(criteria)).mappings().first()
            if row is None:
                now = self._now()
                values = {
                    "job_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "pdf_hash": pdf_hash,
                    "filename": filename,
                    "model": model,
                    "detail": detail,
                    "schema_version": schema_version,
                    "status": JobStatus.PENDING.value,
                    "total_blocks": total_blocks,
                    "created_at": now,
                    "updated_at": now,
                }
                connection.execute(insert(self._jobs).values(**values))
                row = values
            elif row["total_blocks"] != total_blocks or row["filename"] != filename:
                connection.execute(
                    update(self._jobs)
                    .where(self._jobs.c.job_id == row["job_id"])
                    .values(
                        filename=filename,
                        total_blocks=total_blocks,
                        updated_at=self._now(),
                    )
                )
                row = {**row, "filename": filename, "total_blocks": total_blocks}
            return self._to_job(row, self._count_completed(connection, row["job_id"]))

    def get_completed_block(
        self, job_id: str, chunk: PdfChunk
    ) -> tuple[ExtractedBlock, ApiUsage] | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(self._blocks).where(
                    (self._blocks.c.job_id == job_id)
                    & (self._blocks.c.block_index == chunk.index)
                    & (self._blocks.c.chunk_hash == chunk.sha256)
                    & (self._blocks.c.status == BlockStatus.COMPLETED.value)
                )
            ).mappings().first()
        if row is None or not row["result_json"]:
            return None
        return (
            ExtractedBlock.model_validate_json(row["result_json"]),
            ApiUsage(
                input_tokens=int(row["input_tokens"] or 0),
                output_tokens=int(row["output_tokens"] or 0),
                request_id=str(row["request_id"] or ""),
            ),
        )

    def mark_block_processing(self, job_id: str, chunk: PdfChunk) -> None:
        now = self._now()
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(self._blocks.c.attempts).where(
                    (self._blocks.c.job_id == job_id)
                    & (self._blocks.c.block_index == chunk.index)
                )
            ).first()
            values = {
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "chunk_hash": chunk.sha256,
                "status": BlockStatus.PROCESSING.value,
                "error": "",
                "attempts": int(existing[0] if existing else 0) + 1,
                "updated_at": now,
            }
            if existing:
                connection.execute(
                    update(self._blocks)
                    .where(
                        (self._blocks.c.job_id == job_id)
                        & (self._blocks.c.block_index == chunk.index)
                    )
                    .values(**values)
                )
            else:
                connection.execute(
                    insert(self._blocks).values(
                        job_id=job_id,
                        block_index=chunk.index,
                        result_json=None,
                        input_tokens=0,
                        output_tokens=0,
                        request_id="",
                        **values,
                    )
                )
            connection.execute(
                update(self._jobs)
                .where(self._jobs.c.job_id == job_id)
                .values(status=JobStatus.PROCESSING.value, updated_at=now)
            )

    def save_block_success(
        self,
        job_id: str,
        chunk: PdfChunk,
        result: ExtractedBlock,
        usage: ApiUsage,
    ) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(self._blocks)
                .where(
                    (self._blocks.c.job_id == job_id)
                    & (self._blocks.c.block_index == chunk.index)
                )
                .values(
                    status=BlockStatus.COMPLETED.value,
                    result_json=result.model_dump_json(),
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    request_id=usage.request_id,
                    error="",
                    updated_at=self._now(),
                )
            )

    def save_block_error(self, job_id: str, chunk: PdfChunk, error: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(self._blocks)
                .where(
                    (self._blocks.c.job_id == job_id)
                    & (self._blocks.c.block_index == chunk.index)
                )
                .values(
                    status=BlockStatus.ERROR.value,
                    error=error[:4000],
                    updated_at=self._now(),
                )
            )
            connection.execute(
                update(self._jobs)
                .where(self._jobs.c.job_id == job_id)
                .values(status=JobStatus.RETRYABLE_ERROR.value, updated_at=self._now())
            )

    def set_job_status(self, job_id: str, status: JobStatus) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(self._jobs)
                .where(self._jobs.c.job_id == job_id)
                .values(status=status.value, updated_at=self._now())
            )

    def list_jobs(self, user_id: str, limit: int = 50) -> list[JobRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(self._jobs)
                .where(self._jobs.c.user_id == user_id)
                .order_by(self._jobs.c.updated_at.desc())
                .limit(limit)
            ).mappings().all()
            return [
                self._to_job(row, self._count_completed(connection, row["job_id"]))
                for row in rows
            ]

    def get_usage_baseline(
        self,
        *,
        user_id: str,
        model: str,
        detail: str,
        schema_version: str,
    ) -> UsageBaseline | None:
        """Promedia el consumo real de los bloques comparables del mismo usuario."""
        source = self._blocks.join(
            self._jobs, self._blocks.c.job_id == self._jobs.c.job_id
        )
        statement = (
            select(
                func.count(self._blocks.c.block_index).label("sample_blocks"),
                func.avg(self._blocks.c.input_tokens).label("avg_input"),
                func.avg(self._blocks.c.output_tokens).label("avg_output"),
            )
            .select_from(source)
            .where(
                (self._jobs.c.user_id == user_id)
                & (self._jobs.c.model == model)
                & (self._jobs.c.detail == detail)
                & (self._jobs.c.schema_version == schema_version)
                & (self._blocks.c.status == BlockStatus.COMPLETED.value)
                & (self._blocks.c.input_tokens > 0)
            )
        )
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().one()
        sample_blocks = int(row["sample_blocks"] or 0)
        if sample_blocks == 0:
            return None
        return UsageBaseline(
            input_tokens_per_block=float(row["avg_input"] or 0),
            output_tokens_per_block=float(row["avg_output"] or 0),
            sample_blocks=sample_blocks,
        )

    def delete_job(self, job_id: str, user_id: str) -> None:
        """Elimina un trabajo únicamente si pertenece al usuario indicado."""
        with self._engine.begin() as connection:
            owned = connection.execute(
                select(self._jobs.c.job_id).where(
                    (self._jobs.c.job_id == job_id)
                    & (self._jobs.c.user_id == user_id)
                )
            ).first()
            if not owned:
                return
            connection.execute(delete(self._blocks).where(self._blocks.c.job_id == job_id))
            connection.execute(delete(self._jobs).where(self._jobs.c.job_id == job_id))

    def _count_completed(self, connection, job_id: str) -> int:
        rows = connection.execute(
            select(self._blocks.c.block_index).where(
                (self._blocks.c.job_id == job_id)
                & (self._blocks.c.status == BlockStatus.COMPLETED.value)
            )
        ).all()
        return len(rows)

    @staticmethod
    def _to_job(row, completed_blocks: int) -> JobRecord:
        return JobRecord(
            job_id=str(row["job_id"]),
            user_id=str(row["user_id"]),
            pdf_hash=str(row["pdf_hash"]),
            filename=str(row["filename"]),
            model=str(row["model"]),
            detail=str(row["detail"]),
            schema_version=str(row["schema_version"]),
            status=JobStatus(str(row["status"])),
            total_blocks=int(row["total_blocks"]),
            completed_blocks=completed_blocks,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
