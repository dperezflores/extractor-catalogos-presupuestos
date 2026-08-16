"""Autenticación Google y autorización por lista de correos."""

from __future__ import annotations

import streamlit as st

from src.config import AppSettings
from src.domain.models import UserIdentity


class AuthenticationService:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def current_user(self) -> UserIdentity | None:
        if not self._settings.auth_required:
            return UserIdentity(
                user_id="local-development",
                name="Usuario de desarrollo",
                email="local@development",
            )
        try:
            if not st.user.is_logged_in:
                return None
            user_id = str(st.user.get("sub", "")).strip()
            email = str(st.user.get("email", "")).strip().lower()
            name = str(st.user.get("name", email)).strip()
        except (AttributeError, KeyError):
            return None
        if not user_id or not email:
            return None
        return UserIdentity(user_id=user_id, name=name, email=email)

    def is_authorized(self, user: UserIdentity) -> bool:
        if not self._settings.allowed_emails:
            return True
        return user.email in self._settings.allowed_emails

    @staticmethod
    def login() -> None:
        st.login()

    @staticmethod
    def logout() -> None:
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.logout()

