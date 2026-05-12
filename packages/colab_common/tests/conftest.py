"""
Root conftest for colab_common tests.
Sets JWT_SECRET so auth tests don't need a real Secrets Manager.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://colab:colab@localhost:5432/colab_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
