"""Configuración central de la aplicación."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _section(secrets: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = secrets.get(name, {})
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Valores configurables sin mezclar configuración con lógica de negocio."""

    app_name: str = "Extractor inteligente de catálogos"
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"
    pdf_detail: str = "high"
    chunk_size: int = 4
    chunk_overlap: int = 1
    match_threshold: int = 86
    auth_required: bool = True
    allowed_emails: tuple[str, ...] = ()
    database_url: str = "sqlite:///data/checkpoints.db"
    schema_version: str = "catalog-v1"
    input_price_per_million: float = 0.20
    output_price_per_million: float = 1.20
    cost_estimate_margin: float = 0.30
    css_path: Path = PROJECT_ROOT / "assets" / "styles.css"

    @classmethod
    def from_secrets(cls, secrets: Mapping[str, Any]) -> AppSettings:
        defaults = cls()
        application = _section(secrets, "application")
        access = _section(secrets, "access")
        database = _section(secrets, "database")

        allowed = tuple(
            str(email).strip().lower()
            for email in access.get("allowed_emails", [])
            if str(email).strip()
        )
        return cls(
            app_name=str(application.get("app_name", defaults.app_name)),
            model=str(application.get("model", defaults.model)),
            reasoning_effort=str(
                application.get("reasoning_effort", defaults.reasoning_effort)
            ),
            pdf_detail=str(application.get("pdf_detail", defaults.pdf_detail)),
            chunk_size=max(1, int(application.get("chunk_size", defaults.chunk_size))),
            chunk_overlap=max(
                0, int(application.get("chunk_overlap", defaults.chunk_overlap))
            ),
            match_threshold=max(
                0,
                min(100, int(application.get("match_threshold", defaults.match_threshold))),
            ),
            auth_required=bool(application.get("auth_required", defaults.auth_required)),
            allowed_emails=allowed,
            database_url=str(database.get("url", defaults.database_url)),
            input_price_per_million=float(
                application.get(
                    "input_price_per_million", defaults.input_price_per_million
                )
            ),
            output_price_per_million=float(
                application.get(
                    "output_price_per_million", defaults.output_price_per_million
                )
            ),
            cost_estimate_margin=float(
                application.get("cost_estimate_margin", defaults.cost_estimate_margin)
            ),
        )

    def validate(self) -> None:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap debe ser menor que chunk_size.")
        if self.pdf_detail not in {"low", "high", "auto"}:
            raise ValueError("pdf_detail debe ser low, high o auto.")
        if self.reasoning_effort not in {
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("reasoning_effort no es válido.")
        if self.input_price_per_million < 0 or self.output_price_per_million < 0:
            raise ValueError("Las tarifas por millón de tokens no pueden ser negativas.")
        if not 0 <= self.cost_estimate_margin <= 1:
            raise ValueError("El margen de estimación debe estar entre 0 y 1.")
