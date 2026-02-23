"""Tests for the arXiv API client."""

from __future__ import annotations

import textwrap

import pytest

from opencite.clients.arxiv import ArXivClient
from opencite.config import Config


@pytest.fixture
def config() -> Config:
    return Config.from_env()


# ---------------------------------------------------------------------------
# Atom XML fixture (minimal but valid)
# ---------------------------------------------------------------------------

_ATOM_FEED = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/1706.03762v5</id>
        <title>Attention Is All You Need</title>
        <published>2017-06-12T17:57:34Z</published>
        <updated>2017-06-12T17:57:34Z</updated>
        <summary>  The dominant sequence transduction models are based on complex
    recurrent or convolutional neural networks.  </summary>
        <author><name>Ashish Vaswani</name></author>
        <author><name>Noam Shazeer</name></author>
        <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
        <arxiv:primary_category term="cs.CL"
          scheme="http://arxiv.org/schemas/atom"/>
        <arxiv:doi>10.48550/arXiv.1706.03762</arxiv:doi>
        <arxiv:journal_ref>Advances in Neural Information Processing Systems 30 (2017)</arxiv:journal_ref>
      </entry>
    </feed>
""")

_EMPTY_FEED = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
    </feed>
""")


class TestArXivClientParsing:
    """Unit tests for Atom XML parsing (no network required)."""

    def _client(self) -> ArXivClient:
        return ArXivClient(Config())

    def test_parse_feed_basic(self):
        client = self._client()
        papers = client._parse_feed(_ATOM_FEED)
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Attention Is All You Need"
        assert p.ids.arxiv_id == "1706.03762"
        assert p.year == 2017
        assert p.publication_date == "2017-06-12"
        assert len(p.authors) == 2
        assert p.authors[0].name == "Ashish Vaswani"
        assert "cs.CL" in p.topics
        assert p.is_oa is True
        assert p.data_sources == {"arxiv"}

    def test_parse_feed_pdf_url(self):
        client = self._client()
        papers = client._parse_feed(_ATOM_FEED)
        p = papers[0]
        assert p.best_pdf_url == "https://arxiv.org/pdf/1706.03762"

    def test_parse_feed_abstract_stripped(self):
        client = self._client()
        papers = client._parse_feed(_ATOM_FEED)
        abstract = papers[0].abstract
        assert "dominant sequence transduction" in abstract
        # Leading/trailing whitespace stripped
        assert not abstract.startswith(" ")
        assert not abstract.endswith(" ")

    def test_parse_feed_journal_ref_overrides_source(self):
        client = self._client()
        papers = client._parse_feed(_ATOM_FEED)
        p = papers[0]
        # When journal_ref is present, source_venue should reflect it
        assert p.source_venue is not None
        assert "Neural Information Processing" in p.source_venue.name

    def test_parse_feed_doi_from_arxiv_ns(self):
        client = self._client()
        papers = client._parse_feed(_ATOM_FEED)
        assert papers[0].ids.doi == "10.48550/arXiv.1706.03762"

    def test_parse_empty_feed(self):
        client = self._client()
        papers = client._parse_feed(_EMPTY_FEED)
        assert papers == []

    def test_parse_invalid_xml(self):
        client = self._client()
        papers = client._parse_feed("not xml at all <<<<<")
        assert papers == []

    def test_parse_feed_year_filter(self):
        client = self._client()
        # Paper is from 2017; filtering for year >= 2020 should exclude it
        papers = client._parse_feed(_ATOM_FEED, year_from=2020)
        assert papers == []

        # year_to 2020 should include a 2017 paper
        papers = client._parse_feed(_ATOM_FEED, year_to=2020)
        assert len(papers) == 1

    def test_parse_http_and_https_abs_urls(self):
        """arXiv uses http:// in old feeds; ensure both parse correctly."""

        client = self._client()
        for scheme in ("http", "https"):
            feed = _ATOM_FEED.replace(
                "http://arxiv.org/abs/1706.03762v5",
                f"{scheme}://arxiv.org/abs/1706.03762v5",
            )
            papers = client._parse_feed(feed)
            assert papers[0].ids.arxiv_id == "1706.03762", f"Failed for {scheme}://"
