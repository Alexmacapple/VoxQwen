import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    """Client HTTP in-process (pas de serveur live)."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
