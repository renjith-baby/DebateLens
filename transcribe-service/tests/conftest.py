from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from transcribe_service.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
