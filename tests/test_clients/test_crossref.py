"""Tests for the CrossRef API client."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from opencite.clients.base import BaseClient
from opencite.clients.crossref import CrossRefClient, _parse_work
from opencite.config import Config
from opencite.exceptions import APIError

# -- Unit tests for _parse_work (no API needed) --

SAMPLE_WORK = {
    "DOI": "10.1109/tnsre.2010.2041593",
    "title": ["Brain-Computer Interface-Based Robotic End Effector System"],
    "author": [
        {
            "given": "Keng Peng",
            "family": "Tee",
            "ORCID": "https://orcid.org/0000-0001-1234",
        },
        {"given": "Shuzhi Sam", "family": "Ge"},
    ],
    "published-print": {"date-parts": [[2010, 6]]},
    "container-title": [
        "IEEE Transactions on Neural Systems and Rehabilitation Engineering"
    ],
    "ISSN": ["1534-4320"],
    "publisher": "IEEE",
    "type": "journal-article",
    "abstract": "<jats:p>This paper presents a brain-computer interface system.</jats:p>",
    "is-referenced-by-count": 42,
    "link": [
        {
            "URL": "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=5395649",
            "content-type": "application/pdf",
        },
        {
            "URL": "https://ieeexplore.ieee.org/document/5395649",
            "content-type": "text/html",
        },
    ],
}


def test_parse_work_basic_fields():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert paper.title == "Brain-Computer Interface-Based Robotic End Effector System"
    assert paper.doi == "10.1109/tnsre.2010.2041593"
    assert paper.year == 2010
    assert paper.citation_count == 42
    assert "crossref" in paper.data_sources


def test_parse_work_authors():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert len(paper.authors) == 2
    assert paper.authors[0].family_name == "Tee"
    assert paper.authors[0].given_name == "Keng Peng"
    assert paper.authors[0].orcid == "https://orcid.org/0000-0001-1234"


def test_parse_work_venue():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert paper.source_venue is not None
    assert "IEEE" in paper.source_venue.name
    assert paper.source_venue.publisher == "IEEE"
    assert paper.source_venue.issn == "1534-4320"


def test_parse_work_abstract_strips_jats():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert "<jats" not in paper.abstract
    assert "brain-computer interface" in paper.abstract.lower()


def test_parse_work_pdf_links():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert len(paper.pdf_locations) == 1  # only application/pdf
    assert "stampPDF" in paper.pdf_locations[0].url
    assert paper.pdf_locations[0].source == "crossref"


def test_parse_work_no_title():
    assert _parse_work({}) is None
    assert _parse_work({"title": []}) is None


def test_parse_work_minimal():
    paper = _parse_work({"title": ["Some Paper"], "DOI": "10.1234/test"})
    assert paper is not None
    assert paper.title == "Some Paper"
    assert paper.doi == "10.1234/test"
    assert paper.authors == []
    assert paper.source_venue is None


def test_parse_work_publication_date():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert paper.publication_date == "2010-6"


class TestQueryCoalescing:
    """Identical concurrent /works queries share one request."""

    _URL = "https://api.crossref.org/works"
    _PARAMS = {"query": "memory", "rows": 1}

    def setup_method(self):
        BaseClient.reset_shared_limiters()
        CrossRefClient._inflight.clear()

    def teardown_method(self):
        BaseClient.reset_shared_limiters()

    @staticmethod
    def _slow_ok(delay: float):
        async def respond(_request):
            await asyncio.sleep(delay)
            return httpx.Response(200, json={"message": {"items": [{"DOI": "x"}]}})

        return respond

    @respx.mock
    async def test_shared_error_reaches_every_waiter(self):
        route = respx.get(self._URL).mock(return_value=httpx.Response(400))
        async with CrossRefClient(Config()) as client:
            results = await asyncio.gather(
                client.query_works(self._PARAMS),
                client.query_works(self._PARAMS),
                return_exceptions=True,
            )
        assert all(isinstance(r, APIError) for r in results)
        assert route.call_count == 1
        assert CrossRefClient._inflight == {}

    @respx.mock
    async def test_cancelled_first_waiter_leaves_result_for_second(self):
        route = respx.get(self._URL).mock(side_effect=self._slow_ok(0.05))
        async with CrossRefClient(Config()) as client:
            first = asyncio.create_task(client.query_works(self._PARAMS))
            second = asyncio.create_task(client.query_works(self._PARAMS))
            await asyncio.sleep(0.01)
            first.cancel()
            assert await second == [{"DOI": "x"}]
        assert route.call_count == 1
        assert CrossRefClient._inflight == {}

    @respx.mock
    async def test_request_cancelled_when_every_waiter_leaves(self):
        respx.get(self._URL).mock(side_effect=self._slow_ok(1.0))
        async with CrossRefClient(Config()) as client:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(client.query_works(self._PARAMS), 0.05)
            assert CrossRefClient._inflight == {}
        # Let the cancellation land, then nothing may still run against the
        # closed client session.
        await asyncio.sleep(0)
        pending = [
            t for t in asyncio.all_tasks() if not t.done() and "_fetch_works" in repr(t)
        ]
        assert pending == []
