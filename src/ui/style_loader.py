"""Carga el CSS institucional desde un archivo independiente."""

from pathlib import Path

import streamlit as st


class StyleLoader:
    @staticmethod
    def apply(css_path: Path) -> None:
        if not css_path.exists():
            return
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

