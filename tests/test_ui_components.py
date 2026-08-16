import pandas as pd

from src.ui.components import AppComponents


def test_percentage_columns_are_displayed_on_a_zero_to_one_hundred_scale(monkeypatch):
    captured: dict[str, pd.DataFrame] = {}

    monkeypatch.setattr("src.ui.components.st.subheader", lambda _title: None)
    monkeypatch.setattr(
        "src.ui.components.st.dataframe",
        lambda dataframe, **_kwargs: captured.update(dataframe=dataframe),
    )

    source = pd.DataFrame(
        {"Nivel de confianza": [1.0, 0.85], "Coincidencia": [0.94, 0.7]}
    )

    AppComponents.data_table(source, "Resultados")

    assert captured["dataframe"]["Nivel de confianza"].tolist() == [100.0, 85.0]
    assert captured["dataframe"]["Coincidencia"].tolist() == [94.0, 70.0]
    assert source["Nivel de confianza"].tolist() == [1.0, 0.85]
