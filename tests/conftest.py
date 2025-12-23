import pytest


@pytest.fixture
def sample_arena_export() -> str:
    """Sample Arena deck export for testing."""
    return """Deck
4 Lightning Bolt (LEB) 163
4 Monastery Swiftspear (BRO) 144
20 Mountain (NEO) 290

Sideboard
2 Abrade (VOW) 139"""
