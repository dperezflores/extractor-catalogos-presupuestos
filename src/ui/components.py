"""Componentes visuales reutilizables de la aplicación."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from src.domain.models import ProcessingResult, UserIdentity


class AppComponents:
    PERCENTAGE_COLUMNS = ("Nivel de confianza", "Coincidencia")

    @staticmethod
    def header() -> None:
        st.markdown(
            """
            <section class="institutional-header">
                <h1>Extractor inteligente de catálogos</h1>
                <p>Lectura visual de presupuestos, recuperación por bloques y cruce
                opcional de conceptos.</p>
            </section>
            """,
            unsafe_allow_html=True,
        )

    @staticmethod
    def workflow_cards() -> None:
        columns = st.columns(3)
        cards = [
            ("1", "Carga", "PDF obligatorio y Excel de conceptos opcional."),
            ("2", "Extracción", "Luna lee visualmente el presupuesto y guarda cada bloque."),
            ("3", "Resultado", "Visualiza la tabla y descarga los archivos generados."),
        ]
        for column, (number, title, description) in zip(columns, cards, strict=True):
            with column:
                st.markdown(
                    f"""
                    <div class="step-card">
                        <span class="step-number">{number}</span>
                        <h3>{title}</h3>
                        <p>{description}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    @staticmethod
    def user_chip(user: UserIdentity) -> None:
        st.markdown(
            f"""
            <div class="user-chip">
                <strong>{html.escape(user.name)}</strong>
                <span>{html.escape(user.email)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    @staticmethod
    def result_metrics(result: ProcessingResult) -> None:
        extracted = sum(row.status.value == "Extraído" for row in result.catalog)
        review = sum(row.status.value == "Revisar" for row in result.catalog)
        unreadable = sum(row.status.value == "No legible" for row in result.catalog)
        cols = st.columns(4)
        cols[0].metric("Conceptos", len(result.catalog))
        cols[1].metric("Extraídos", extracted)
        cols[2].metric("Revisar", review)
        cols[3].metric("No legibles", unreadable)

    @staticmethod
    def data_table(dataframe: pd.DataFrame, title: str) -> None:
        st.subheader(title)
        display_dataframe = dataframe.copy()
        for column_name in AppComponents.PERCENTAGE_COLUMNS:
            if column_name in display_dataframe.columns:
                display_dataframe[column_name] = (
                    pd.to_numeric(display_dataframe[column_name], errors="coerce") * 100
                )

        available_config = {
            "Cantidad": st.column_config.NumberColumn(format="%.4f"),
            "Precio unitario": st.column_config.NumberColumn(format="$ %.2f"),
            "Precio unitario (PDF)": st.column_config.NumberColumn(format="$ %.2f"),
            "Nivel de confianza": st.column_config.ProgressColumn(
                min_value=0.0, max_value=100.0, format="%.0f%%"
            ),
            "Coincidencia": st.column_config.ProgressColumn(
                min_value=0.0, max_value=100.0, format="%.0f%%"
            ),
        }
        column_config = {
            name: config
            for name, config in available_config.items()
            if name in dataframe.columns
        }
        st.dataframe(
            display_dataframe,
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
        )
