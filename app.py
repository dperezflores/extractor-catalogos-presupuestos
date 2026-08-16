"""Punto de entrada único de la aplicación Streamlit."""

from src.application import CatalogApplication


def main() -> None:
    CatalogApplication().run()


if __name__ == "__main__":
    main()
