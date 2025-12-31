import pytest

from forgebreaker.models import failure as failure_module


@pytest.fixture(autouse=True)
def clear_finalized_responses():
    """Clear the finalized responses set between tests.

    This prevents test isolation issues where Python reuses memory
    addresses for new objects, causing id() collisions with previously
    finalized responses.
    """
    failure_module._finalized_responses.clear()
    yield
    failure_module._finalized_responses.clear()


@pytest.fixture
def sample_arena_export() -> str:
    """Sample Arena deck export for testing."""
    return """Deck
4 Lightning Bolt (LEB) 163
4 Monastery Swiftspear (BRO) 144
20 Mountain (NEO) 290

Sideboard
2 Abrade (VOW) 139"""
