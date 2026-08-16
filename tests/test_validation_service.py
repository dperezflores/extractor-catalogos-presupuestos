from src.domain.models import ExtractedConcept, ExtractionStatus, LocatedConcept
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


def test_review_concept_reports_source_page_range() -> None:
    located = LocatedConcept(
        concept(precio_unitario="", legible=False, observacion="Precio borroso"),
        page_start=21,
        page_end=24,
    )

    row = CatalogValidator().validate_and_merge([located])[0]

    assert row.status == ExtractionStatus.UNREADABLE
    assert row.pdf_location == "Páginas 21–24"


def test_overlap_duplicate_narrows_location_to_shared_page() -> None:
    ambiguous = concept(unidad="", observacion="Revisar unidad")
    rows = CatalogValidator().validate_and_merge(
        [
            LocatedConcept(ambiguous, page_start=1, page_end=4),
            LocatedConcept(ambiguous, page_start=4, page_end=7),
        ]
    )

    assert len(rows) == 1
    assert rows[0].status == ExtractionStatus.REVIEW
    assert rows[0].pdf_location == "Página 4"
