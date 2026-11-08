import io
import json
import urllib.error
from urllib.parse import parse_qs, urlparse

import pytest

import settings
from website import cache

TOKEN = 'vcp_secret_token_value'


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    def __init__(self, fail_with=None):
        self.requests = []
        self.fail_with = fail_with

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.fail_with:
            raise self.fail_with
        return FakeResponse(b'{}')


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, 'VERCEL_API_TOKEN', TOKEN)
    monkeypatch.setattr(settings, 'VERCEL_PROJECT_ID', 'prj_123')


def test_tests_never_have_a_real_token():
    assert not cache.configured()


def test_without_settings_nothing_is_sent():
    opener = Recorder()

    with pytest.raises(cache.PurgeError, match='not set'):
        cache.purge_pages(opener)

    assert opener.requests == []


@pytest.mark.usefixtures('configured')
def test_deletes_the_pages_tag_in_production_and_preview():
    opener = Recorder()

    cache.purge_pages(opener)

    targets = []
    for request, timeout in opener.requests:
        url = urlparse(request.full_url)
        assert request.method == 'POST'
        assert f'{url.scheme}://{url.netloc}{url.path}' == (
            'https://api.vercel.com/v1/edge-cache/dangerously-delete-by-tags'
        )
        assert parse_qs(url.query) == {'projectIdOrName': ['prj_123']}
        assert request.get_header('Authorization') == f'Bearer {TOKEN}'
        assert request.get_header('Content-type') == 'application/json'
        body = json.loads(request.data)
        assert body['tags'] == ['pages']
        targets.append(body['target'])
        assert timeout == cache.TIMEOUT_SECONDS

    assert targets == ['production', 'preview']


@pytest.mark.usefixtures('configured')
def test_team_id_is_sent_when_set(monkeypatch):
    monkeypatch.setattr(settings, 'VERCEL_TEAM_ID', 'team_9')
    opener = Recorder()

    cache.purge_pages(opener)

    query = parse_qs(urlparse(opener.requests[0][0].full_url).query)
    assert query == {'projectIdOrName': ['prj_123'], 'teamId': ['team_9']}


@pytest.mark.usefixtures('configured')
def test_an_error_names_the_status_but_never_the_token():
    error = urllib.error.HTTPError('url', 403, 'Forbidden', {}, None)

    with pytest.raises(cache.PurgeError) as raised:
        cache.purge_pages(Recorder(fail_with=error))

    assert 'answered 403 for production' in str(raised.value)
    assert TOKEN not in str(raised.value)


@pytest.mark.usefixtures('configured')
def test_an_unreachable_api_is_a_purge_error():
    with pytest.raises(cache.PurgeError, match='could not reach Vercel'):
        cache.purge_pages(Recorder(fail_with=urllib.error.URLError('timed out')))
