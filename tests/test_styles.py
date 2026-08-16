from src.config import PROJECT_ROOT


def test_progress_bar_uses_conventional_blue() -> None:
    styles = (PROJECT_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "--progress-blue: #1976D2" in styles
    assert 'div[data-testid="stProgress"]' in styles
