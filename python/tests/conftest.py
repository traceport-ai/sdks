import pytest

from .helpers import Harness


@pytest.fixture(params=["sync", "async"])
def mode(request):
    return request.param


@pytest.fixture
async def make(mode):
    clients = []

    def create(steps, **options):
        client = Harness(mode, steps, **options)
        clients.append(client)
        return client

    yield create
    for client in clients:
        await client.close()
