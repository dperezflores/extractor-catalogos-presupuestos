"""Composición de dependencias y control de la interfaz principal."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from openai import APIConnectionError, AuthenticationError, RateLimitError

from src.config import AppSettings
from src.domain.models import (
    ExcelSearchField,
    ProcessingPlan,
    ProcessingResult,
    UserIdentity,
)
from src.repositories.checkpoint_repository import SqlCheckpointRepository
from src.services.auth_service import AuthenticationService
from src.services.excel_service import ExcelService
from src.services.matching_service import ConceptMatcher
from src.services.pdf_service import PdfChunker, PdfProcessingError
from src.services.processing_service import CatalogProcessingService
from src.services.validation_service import CatalogValidator
from src.ui.components import AppComponents
from src.ui.style_loader import StyleLoader


@st.cache_resource(show_spinner=False)
def _repository(database_url: str) -> SqlCheckpointRepository:
    return SqlCheckpointRepository(database_url)


class CatalogApplication:
    def run(self) -> None:
        st.set_page_config(
            page_title="Extractor de catálogos",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="expanded",
        )
        settings = self._settings()
        settings.validate()
        StyleLoader.apply(settings.css_path)

        auth = AuthenticationService(settings)
        user = auth.current_user()
        if user is None:
            self._render_login(auth)
            return
        if not auth.is_authorized(user):
            self._render_unauthorized(user, auth)
            return

        repository = _repository(settings.database_url)
        processing_service = CatalogProcessingService(
            settings=settings,
            repository=repository,
            chunker=PdfChunker(settings.chunk_size, settings.chunk_overlap),
            validator=CatalogValidator(),
        )
        excel_service = ExcelService()
        matcher = ConceptMatcher(settings.match_threshold)

        self._render_sidebar(user, auth, processing_service, settings)
        AppComponents.header()
        AppComponents.workflow_cards()
        st.write("")

        if not st.session_state.get("api_key_valid", False):
            st.info("Ingresa y valida tu API key en la barra lateral para comenzar.")
            return

        new_tab, history_tab = st.tabs(["Nuevo procesamiento", "Mis procesamientos"])
        with new_tab:
            self._render_new_job(user, processing_service, excel_service, matcher)
        with history_tab:
            self._render_history(user, repository)

    @staticmethod
    def _settings() -> AppSettings:
        try:
            secrets: dict[str, Any] = st.secrets.to_dict()
        except (FileNotFoundError, AttributeError):
            secrets = {"application": {"auth_required": False}}
        return AppSettings.from_secrets(secrets)

    @staticmethod
    def _render_login(auth: AuthenticationService) -> None:
        st.markdown(
            """
            <div class="login-shell">
                <h1>Extractor de catálogos</h1>
                <p>Acceso exclusivo para usuarios autorizados.</p>
                <p class="muted-note">La aplicación solamente solicitará nombre y
                correo verificado.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _, center, _ = st.columns([1, 1, 1])
        with center:
            st.button(
                "Ingresar con Google",
                type="primary",
                use_container_width=True,
                on_click=auth.login,
            )

    @staticmethod
    def _render_unauthorized(user: UserIdentity, auth: AuthenticationService) -> None:
        st.error(f"La cuenta {user.email} no está autorizada para usar esta aplicación.")
        st.button("Cerrar sesión", on_click=auth.logout)

    def _render_sidebar(
        self,
        user: UserIdentity,
        auth: AuthenticationService,
        processing_service: CatalogProcessingService,
        settings: AppSettings,
    ) -> None:
        with st.sidebar:
            st.markdown("### Sesión")
            AppComponents.user_chip(user)
            if st.button("Cerrar sesión", use_container_width=True):
                auth.logout()

            st.markdown("### OpenAI")
            if st.session_state.get("api_key_valid", False):
                st.success("API key validada")
                st.caption(f"Modelo: {settings.model}")
                if st.button("Cambiar API key", use_container_width=True):
                    st.session_state.pop("openai_api_key", None)
                    st.session_state.pop("api_key_valid", None)
                    st.rerun()
            else:
                candidate = st.text_input(
                    "API key",
                    type="password",
                    placeholder="sk-...",
                    help="Se conserva únicamente durante esta sesión.",
                    key="api_key_candidate",
                )
                if st.button("Validar API key", type="primary", use_container_width=True):
                    if not candidate.strip():
                        st.warning("Escribe una API key.")
                    else:
                        with st.spinner("Validando acceso..."):
                            try:
                                processing_service.validate_api_key(candidate.strip())
                            except AuthenticationError:
                                st.error("La API key no es válida.")
                            except Exception as exc:
                                st.error(self._safe_error(exc))
                            else:
                                st.session_state["openai_api_key"] = candidate.strip()
                                st.session_state["api_key_valid"] = True
                                st.rerun()

            st.markdown("---")
            st.caption("La clave no se guarda en GitHub, archivos ni base de datos.")

    def _render_new_job(
        self,
        user: UserIdentity,
        processing_service: CatalogProcessingService,
        excel_service: ExcelService,
        matcher: ConceptMatcher,
    ) -> None:
        st.subheader("Archivos de entrada")
        left, right = st.columns(2)
        with left:
            pdf_file = st.file_uploader(
                "Presupuesto en PDF *",
                type=["pdf"],
                help="Obligatorio. Puede ser un PDF escaneado.",
            )
        with right:
            excel_file = st.file_uploader(
                "Conceptos para buscar (opcional)",
                type=["xlsx"],
                help="La clave debe estar en A y el concepto o descripción en B.",
            )

        search_field = ExcelSearchField.DESCRIPTION
        if excel_file is not None:
            selected_search_field = st.radio(
                "Buscar los precios usando",
                options=[field.value for field in ExcelSearchField],
                index=1,
                horizontal=True,
                help=(
                    "Por clave se exige coincidencia exacta, ignorando mayúsculas y "
                    "separadores. Por descripción se utiliza coincidencia textual."
                ),
            )
            search_field = ExcelSearchField(selected_search_field)

        pdf_hash = PdfChunker.file_hash(pdf_file.getvalue()) if pdf_file is not None else ""
        plan = st.session_state.get("processing_plan")
        if isinstance(plan, ProcessingPlan) and plan.pdf_hash != pdf_hash:
            st.session_state.pop("processing_plan", None)
            plan = None

        preview_clicked = st.button(
            "Revisar consumo antes de procesar",
            type="primary",
            use_container_width=True,
            disabled=pdf_file is None,
        )
        if preview_clicked and pdf_file is not None:
            try:
                plan = processing_service.preview(
                    user=user,
                    pdf_bytes=pdf_file.getvalue(),
                    filename=pdf_file.name,
                )
            except PdfProcessingError as exc:
                st.error(str(exc))
                plan = None
            except Exception as exc:
                st.error(self._safe_error(exc))
                plan = None
            if plan is not None:
                st.session_state["processing_plan"] = plan

        process_clicked = False
        if isinstance(plan, ProcessingPlan):
            AppComponents.processing_plan(plan, processing_service.model)
            confirmed = True
            if plan.pending_blocks:
                confirmed = st.checkbox(
                    "Confirmo que deseo enviar los bloques pendientes a la API "
                    "y generar el consumo correspondiente.",
                    key=f"confirm_api_cost_{plan.pdf_hash}",
                )
            process_clicked = st.button(
                "Confirmar y procesar" if plan.pending_blocks else "Procesar usando caché",
                type="primary",
                use_container_width=True,
                disabled=not confirmed,
            )

        if process_clicked and pdf_file is not None:
            self._process_files(
                user=user,
                processing_service=processing_service,
                excel_service=excel_service,
                matcher=matcher,
                pdf_file=pdf_file,
                excel_file=excel_file,
                search_field=search_field,
            )

        result = st.session_state.get("processing_result")
        if isinstance(result, ProcessingResult):
            self._render_results(result)

    def _process_files(
        self,
        *,
        user: UserIdentity,
        processing_service: CatalogProcessingService,
        excel_service: ExcelService,
        matcher: ConceptMatcher,
        pdf_file,
        excel_file,
        search_field: ExcelSearchField,
    ) -> None:
        progress_bar = st.progress(0.0)
        status_box = st.empty()

        def update_progress(done: int, total: int, message: str) -> None:
            progress_bar.progress(done / total if total else 0.0)
            status_box.caption(message)

        try:
            result = processing_service.process(
                user=user,
                api_key=st.session_state["openai_api_key"],
                pdf_bytes=pdf_file.getvalue(),
                filename=pdf_file.name,
                progress=update_progress,
            )
            catalog_excel = excel_service.catalog_to_excel(result.catalog)
            catalog_df = excel_service.catalog_dataframe(result.catalog)
            st.session_state["processing_result"] = result
            st.session_state["catalog_excel"] = catalog_excel
            st.session_state["catalog_df"] = catalog_df
            st.session_state["catalog_filename"] = self._output_name(
                pdf_file.name, "_catalogo_extraido.xlsx"
            )

            if excel_file is not None:
                crossed_excel, crossed_df = excel_service.cross_reference_excel(
                    excel_file.getvalue(), result.catalog, matcher, search_field
                )
                st.session_state["crossed_excel"] = crossed_excel
                st.session_state["crossed_df"] = crossed_df
                st.session_state["crossed_filename"] = self._output_name(
                    excel_file.name, "_con_precios.xlsx"
                )
            else:
                for key in ("crossed_excel", "crossed_df", "crossed_filename"):
                    st.session_state.pop(key, None)
        except PdfProcessingError as exc:
            st.error(str(exc))
        except AuthenticationError:
            st.session_state.pop("api_key_valid", None)
            st.error("La API key dejó de ser válida. Introdúcela nuevamente.")
        except RateLimitError:
            st.error(
                "Se alcanzó temporalmente el límite de la API. El avance guardado se "
                "conservará y podrás continuar después."
            )
        except APIConnectionError:
            st.error(
                "No fue posible conectar con OpenAI. Los bloques completados permanecen guardados."
            )
        except Exception as exc:
            st.error(self._safe_error(exc))
        else:
            st.session_state.pop("processing_plan", None)
            progress_bar.progress(1.0)
            status_box.success("Procesamiento completado")
            st.success("El catálogo está listo para revisión y descarga.")

    @staticmethod
    def _render_results(result: ProcessingResult) -> None:
        st.markdown("---")
        AppComponents.result_metrics(result)
        st.caption(
            f"Bloques recuperados: {result.cached_blocks} · "
            f"Bloques enviados a la API: {result.processed_blocks} · "
            f"Tokens de entrada: {result.usage.input_tokens:,} · "
            f"Tokens de salida: {result.usage.output_tokens:,}"
        )
        catalog_df = st.session_state.get("catalog_df")
        if isinstance(catalog_df, pd.DataFrame):
            AppComponents.data_table(catalog_df, "Catálogo extraído")
        st.download_button(
            "Descargar catálogo completo",
            data=st.session_state["catalog_excel"],
            file_name=st.session_state["catalog_filename"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )

        crossed_df = st.session_state.get("crossed_df")
        if isinstance(crossed_df, pd.DataFrame):
            AppComponents.data_table(crossed_df, "Cruce de conceptos solicitado")
            st.download_button(
                "Descargar Excel con precios encontrados",
                data=st.session_state["crossed_excel"],
                file_name=st.session_state["crossed_filename"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        if st.button("Limpiar resultado de la pantalla"):
            for key in (
                "processing_result",
                "catalog_excel",
                "catalog_df",
                "catalog_filename",
                "crossed_excel",
                "crossed_df",
                "crossed_filename",
            ):
                st.session_state.pop(key, None)
            st.rerun()

    @staticmethod
    def _render_history(user: UserIdentity, repository: SqlCheckpointRepository) -> None:
        jobs = repository.list_jobs(user.user_id)
        if not jobs:
            st.info("Todavía no tienes procesamientos guardados.")
            return
        dataframe = pd.DataFrame(
            [
                {
                    "Archivo": job.filename,
                    "Estado": job.status.value,
                    "Avance": job.completed_blocks / job.total_blocks
                    if job.total_blocks
                    else 0,
                    "Modelo": job.model,
                    "Actualizado": job.updated_at,
                }
                for job in jobs
            ]
        )
        st.dataframe(
            dataframe,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Avance": st.column_config.ProgressColumn(
                    min_value=0.0, max_value=1.0, format="%.0f%%"
                ),
                "Actualizado": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            },
        )
        st.caption(
            "Para continuar un trabajo incompleto, vuelve a la pestaña anterior "
            "y carga el mismo PDF."
        )

    @staticmethod
    def _output_name(original_name: str, suffix: str) -> str:
        stem = Path(original_name).stem
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "resultado"
        return f"{safe_stem}{suffix}"

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc)
        message = re.sub(r"sk-[A-Za-z0-9_-]+", "[API KEY OCULTA]", message)
        if len(message) > 500:
            message = message[:500] + "…"
        return f"No fue posible completar la operación: {message}"
