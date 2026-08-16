from io import BytesIO

from openpyxl import Workbook, load_workbook

from src.domain.models import CatalogRow, ExtractionStatus
from src.services.excel_service import ExcelService
from src.services.matching_service import ConceptMatcher


def sample_catalog() -> list[CatalogRow]:
    return [
        CatalogRow(
            key="A-01",
            description="Suministro y colocación de concreto hidráulico",
            unit="m3",
            quantity=10,
            unit_price=1450.75,
            status=ExtractionStatus.EXTRACTED,
            confidence=100,
        )
    ]


def input_excel() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "Clave"
    sheet["B1"] = "Concepto"
    sheet["B2"] = "Suministro y colocación de concreto hidráulico"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_catalog_excel_has_expected_columns() -> None:
    content = ExcelService().catalog_to_excel(sample_catalog())
    sheet = load_workbook(BytesIO(content)).active
    assert sheet["A1"].value == "Clave del concepto"
    assert sheet["G1"].value == "Nivel de confianza"


def test_optional_excel_gets_price_column() -> None:
    content, preview = ExcelService().cross_reference_excel(
        input_excel(), sample_catalog(), ConceptMatcher()
    )
    sheet = load_workbook(BytesIO(content)).active
    assert sheet["C1"].value == "Precio unitario (PDF)"
    assert sheet["C2"].value == 1450.75
    assert preview.iloc[0]["Estado"] == "Encontrado"

