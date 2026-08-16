"""Cruce opcional de conceptos usando texto y controles numéricos críticos."""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from src.domain.models import CatalogRow, MatchResult
from src.services.validation_service import CatalogValidator


class ConceptMatcher:
    def __init__(self, threshold: int = 86) -> None:
        self._threshold = threshold
        self._normalizer = CatalogValidator()

    def match(self, query: str, catalog: list[CatalogRow]) -> MatchResult:
        normalized_query = self._normalizer.normalize_text(query)
        if not normalized_query:
            return MatchResult(unit_price=None)

        searchable = {
            index: self._normalizer.normalize_text(row.description)
            for index, row in enumerate(catalog)
            if row.description and row.unit_price is not None
        }
        exact = next(
            (index for index, description in searchable.items() if description == normalized_query),
            None,
        )
        if exact is not None:
            row = catalog[exact]
            return MatchResult(
                unit_price=row.unit_price,
                matched_description=row.description,
                score=100.0,
                status="Encontrado",
            )

        candidate = process.extractOne(
            normalized_query,
            searchable,
            scorer=fuzz.WRatio,
            score_cutoff=self._threshold,
        )
        if candidate is None:
            return MatchResult(unit_price=None)
        _, score, index = candidate
        row = catalog[int(index)]
        if not self._critical_numbers_match(normalized_query, searchable[int(index)]):
            return MatchResult(
                unit_price=None,
                matched_description=row.description,
                score=float(score),
                status="Revisar",
            )
        return MatchResult(
            unit_price=row.unit_price,
            matched_description=row.description,
            score=float(score),
            status="Encontrado" if score >= 93 else "Revisar",
        )

    def match_key(self, query: str, catalog: list[CatalogRow]) -> MatchResult:
        normalized_query = self._normalize_key(query)
        if not normalized_query:
            return MatchResult(unit_price=None)

        for row in catalog:
            if row.unit_price is None or not row.key:
                continue
            if self._normalize_key(row.key) == normalized_query:
                return MatchResult(
                    unit_price=row.unit_price,
                    matched_description=row.description,
                    score=100.0,
                    status="Encontrado",
                )
        return MatchResult(unit_price=None)

    @staticmethod
    def _normalize_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    @staticmethod
    def _critical_numbers_match(left: str, right: str) -> bool:
        numbers_left = set(re.findall(r"\d+(?:[.,]\d+)?", left))
        numbers_right = set(re.findall(r"\d+(?:[.,]\d+)?", right))
        return numbers_left == numbers_right
