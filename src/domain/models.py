"""Entidades y contratos de datos usados por toda la aplicación."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExtractionStatus(StrEnum):
    EXTRACTED = "Extraído"
    REVIEW = "Revisar"
    UNREADABLE = "No legible"


class JobStatus(StrEnum):
    PENDING = "PENDIENTE"
    PROCESSING = "PROCESANDO"
    COMPLETED = "COMPLETADO"
    RETRYABLE_ERROR = "ERROR_REINTENTABLE"
    FATAL_ERROR = "ERROR_DEFINITIVO"


class BlockStatus(StrEnum):
    PENDING = "PENDIENTE"
    PROCESSING = "PROCESANDO"
    COMPLETED = "COMPLETADO"
    ERROR = "ERROR"


class ExcelSearchField(StrEnum):
    KEY = "Clave (columna A)"
    DESCRIPTION = "Concepto o descripción (columna B)"


class ExtractedConcept(BaseModel):
    """Respuesta exacta solicitada al modelo para una fila del presupuesto."""

    model_config = ConfigDict(extra="forbid")

    clave: str = Field(description="Clave exacta del concepto; vacío si no es legible")
    descripcion: str = Field(description="Descripción completa uniendo todos sus renglones")
    unidad: str = Field(description="Unidad exacta reportada en la tabla")
    cantidad: str = Field(
        description="Cantidad en formato decimal canónico, sin separadores de miles"
    )
    precio_unitario: str = Field(
        description=(
            "Precio unitario en formato decimal canónico, sin moneda ni separadores de miles"
        )
    )
    legible: bool = Field(description="Verdadero cuando los cinco campos pueden leerse")
    observacion: str = Field(
        description="Explicación breve de cualquier ambigüedad; vacío cuando no existe"
    )


class ExtractedBlock(BaseModel):
    """Salida estructurada completa de un bloque de páginas."""

    model_config = ConfigDict(extra="forbid")

    conceptos: list[ExtractedConcept]
    advertencias: list[str]


@dataclass(frozen=True, slots=True)
class UserIdentity:
    user_id: str
    name: str
    email: str


@dataclass(frozen=True, slots=True)
class PdfChunk:
    index: int
    page_start: int
    page_end: int
    content: bytes
    sha256: str


@dataclass(slots=True)
class CatalogRow:
    key: str
    description: str
    unit: str
    quantity: float | None
    unit_price: float | None
    status: ExtractionStatus
    confidence: int
    readable: bool = True
    note: str = ""


@dataclass(frozen=True, slots=True)
class ApiUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    request_id: str = ""

    def __add__(self, other: ApiUsage) -> ApiUsage:
        return ApiUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True, slots=True)
class BlockExtractionResult:
    block: ExtractedBlock
    usage: ApiUsage


@dataclass(slots=True)
class JobRecord:
    job_id: str
    user_id: str
    pdf_hash: str
    filename: str
    model: str
    detail: str
    schema_version: str
    status: JobStatus
    total_blocks: int
    completed_blocks: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class MatchResult:
    unit_price: float | None
    matched_description: str = ""
    score: float = 0.0
    status: str = "No localizado"


@dataclass(slots=True)
class ProcessingResult:
    job: JobRecord
    catalog: list[CatalogRow]
    usage: ApiUsage
    cached_blocks: int
    processed_blocks: int


@dataclass(frozen=True, slots=True)
class ProcessingPlan:
    pdf_hash: str
    total_pages: int
    total_blocks: int
    cached_blocks: int
    pending_blocks: int


ProgressCallback = Callable[[int, int, str], None]
