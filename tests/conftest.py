import pytest


def pytest_collection_modifyitems(items):
    """Anything under tests/integration/ is an integration test, marked or not."""
    for item in items:
        if "integration" in str(item.path):
            item.add_marker(pytest.mark.integration)
