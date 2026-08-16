from src.domain.models import ExtractedConcept, ExtractionStatus
from src.services.validation_service import CatalogValidator


def concept(**overrides):
    values = {
        "clave": "PAV-001",
        "descripcion": "Suministro y colocación de concreto hidráulico",
        "unidad": "m3",
        "cantidad": "12.5000",
        "precio_unitario": "1450.75",
        "legible": True,
        "observacion": "",
    }
    values.update(overrides)
    return ExtractedConcept(**values)


def test_valid_concept_is_extracted() -> None:
    row = CatalogValidator().validate_and_merge([concept()])[0]
    assert row.status == ExtractionStatus.EXTRACTED
    assert row.quantity == 12.5
    assert row.unit_price == 1450.75
    assert row.confidence == 100


def test_unreadable_price_requires_review() -> None:
    row = CatalogValidator().validate_and_merge(
        [concept(precio_unitario="", legible=False, observacion="Precio borroso")]
    )[0]
    assert row.unit_price is None
    assert row.status == ExtractionStatus.UNREADABLE


def test_overlap_duplicates_are_removed() -> None:
    rows = CatalogValidator().validate_and_merge([concept(), concept()])
    assert len(rows) == 1

