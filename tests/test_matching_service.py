from src.domain.models import CatalogRow, ExtractionStatus
from src.services.matching_service import ConceptMatcher


def row(description: str, price: float = 100.0) -> CatalogRow:
    return CatalogRow(
        key="A-01",
        description=description,
        unit="m",
        quantity=10,
        unit_price=price,
        status=ExtractionStatus.EXTRACTED,
        confidence=100,
    )


def test_exact_match_returns_price() -> None:
    result = ConceptMatcher().match(
        "Suministro de tubería de 25 mm", [row("Suministro de tubería de 25 mm")]
    )
    assert result.status == "Encontrado"
    assert result.unit_price == 100.0


def test_numeric_difference_does_not_assign_price() -> None:
    result = ConceptMatcher(threshold=70).match(
        "Suministro de tubería de 25 mm", [row("Suministro de tubería de 32 mm")]
    )
    assert result.status in {"Revisar", "No localizado"}
    assert result.unit_price is None


def test_key_match_ignores_case_and_separators() -> None:
    result = ConceptMatcher().match_key(
        "a 01",
        [row("Suministro de tubería")],
    )
    assert result.status == "Encontrado"
    assert result.unit_price == 100.0


def test_key_match_does_not_assign_a_similar_key() -> None:
    result = ConceptMatcher().match_key(
        "A-02",
        [row("Suministro de tubería")],
    )
    assert result.status == "No localizado"
    assert result.unit_price is None
