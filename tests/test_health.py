"""Smoke test for application startup."""


def test_app_imports() -> None:
    """Verify the app can be imported without errors."""
    from forgebreaker.main import app

    assert app.title == "ForgeBreaker"
