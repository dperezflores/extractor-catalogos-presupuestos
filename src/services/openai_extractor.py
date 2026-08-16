"""Integración aislada con OpenAI para lectura visual de cada bloque PDF."""

from __future__ import annotations

import base64
from typing import Any

from openai import OpenAI

from src.domain.models import (
    ApiUsage,
    BlockExtractionResult,
    ExtractedBlock,
    PdfChunk,
)

SYSTEM_PROMPT = """
Eres un especialista en presupuestos de obra pública y análisis de precios unitarios.
Lee visualmente las páginas del PDF y extrae todas las filas que correspondan a
conceptos del catálogo de obra.

Reglas obligatorias:
1. Extrae únicamente: clave, descripción completa, unidad, cantidad y precio unitario.
2. Une en una sola descripción todos los renglones pertenecientes al mismo concepto.
3. No confundas cantidad, precio unitario e importe total. No devuelvas el importe.
4. Conserva exactamente las letras, números, guiones, diámetros y dimensiones de la clave
   y de la descripción.
5. Devuelve cantidad y precio como texto decimal canónico: punto decimal, sin símbolo de
   moneda y sin separadores de miles. Ejemplo: 1234.56.
6. No extraigas encabezados, subtotales, totales, firmas, notas ni títulos de capítulos.
7. No inventes información. Si un campo no es legible, déjalo vacío, marca legible=false
   y explica la ambigüedad en observacion.
8. Si una fila parece continuar fuera del bloque, extrae únicamente lo que sea verificable
   y agrega una advertencia.
9. Si no existen conceptos en estas páginas, devuelve una lista vacía.
""".strip()


class OpenAICatalogExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        detail: str,
        reasoning_effort: str,
    ) -> None:
        self._client = OpenAI(api_key=api_key, max_retries=1, timeout=300.0)
        self._model = model
        self._detail = detail
        self._reasoning_effort = reasoning_effort

    def validate_credentials(self) -> None:
        """Comprueba autenticación y acceso al modelo sin generar contenido."""
        self._client.models.retrieve(self._model)

    def extract(self, chunk: PdfChunk) -> BlockExtractionResult:
        encoded = base64.b64encode(chunk.content).decode("ascii")
        response = self._client.responses.parse(
            model=self._model,
            reasoning={"effort": self._reasoning_effort},
            store=False,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": (
                                f"presupuesto_paginas_{chunk.page_start}_{chunk.page_end}.pdf"
                            ),
                            "file_data": f"data:application/pdf;base64,{encoded}",
                            "detail": self._detail,
                        },
                        {
                            "type": "input_text",
                            "text": (
                                "Extrae el catálogo visible en las páginas "
                                f"{chunk.page_start} a {chunk.page_end}."
                            ),
                        },
                    ],
                },
            ],
            text_format=ExtractedBlock,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("OpenAI no devolvió una respuesta estructurada.")
        usage = self._read_usage(response)
        return BlockExtractionResult(block=parsed, usage=usage)

    @staticmethod
    def _read_usage(response: Any) -> ApiUsage:
        usage = getattr(response, "usage", None)
        return ApiUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            request_id=str(getattr(response, "_request_id", "") or ""),
        )

