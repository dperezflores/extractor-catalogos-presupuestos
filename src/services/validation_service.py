"""Validaciones deterministas que no consumen API."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from src.domain.models import CatalogRow, ExtractedConcept, ExtractionStatus


class CatalogValidator:
    def validate_and_merge(self, concepts: list[ExtractedConcept]) -> list[CatalogRow]:
        rows = [self._validate(item) for item in concepts]
        return self._deduplicate(rows)

    def _validate(self, item: ExtractedConcept) -> CatalogRow:
        quantity = self.parse_decimal(item.cantidad)
        unit_price = self.parse_decimal(item.precio_unitario)
        confidence = 100

        if not item.legible:
            confidence -= 35
        if not item.clave.strip():
            confidence -= 25
        if len(item.descripcion.strip()) < 15:
            confidence -= 25
        if not item.unidad.strip():
            confidence -= 15
        if quantity is None:
            confidence -= 20
        if unit_price is None:
            confidence -= 30
        if item.observacion.strip():
            confidence -= 10

        confidence = max(0, min(100, confidence))
        if confidence >= 90:
            status = ExtractionStatus.EXTRACTED
        elif confidence >= 70:
            status = ExtractionStatus.REVIEW
        else:
            status = ExtractionStatus.UNREADABLE

        return CatalogRow(
            key=self._clean_text(item.clave),
            description=self._clean_text(item.descripcion),
            unit=self._clean_text(item.unidad),
            quantity=float(quantity) if quantity is not None else None,
            unit_price=float(unit_price) if unit_price is not None else None,
            status=status,
            confidence=confidence,
            readable=item.legible,
            note=self._clean_text(item.observacion),
        )

    def _deduplicate(self, rows: list[CatalogRow]) -> list[CatalogRow]:
        selected: dict[tuple[str, str], CatalogRow] = {}
        order: list[tuple[str, str]] = []
        for row in rows:
            identity = (
                self.normalize_text(row.key),
                self.normalize_text(row.description),
            )
            if identity not in selected:
                selected[identity] = row
                order.append(identity)
            elif row.confidence > selected[identity].confidence:
                selected[identity] = row
        return [selected[identity] for identity in order]

    @staticmethod
    def parse_decimal(value: str) -> Decimal | None:
        cleaned = re.sub(r"[^0-9,.-]", "", str(value or "").strip())
        if not cleaned or cleaned in {"-", ".", ","}:
            return None
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(".") > cleaned.rfind(","):
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            parts = cleaned.split(",")
            if len(parts) == 2 and len(parts[1]) <= 4:
                cleaned = ".".join(parts)
            else:
                cleaned = "".join(parts)
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def normalize_text(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", str(value or ""))
        without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
        lowered = without_accents.lower()
        return re.sub(r"[^a-z0-9]+", " ", lowered).strip()

