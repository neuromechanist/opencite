"""Tests for opencite.utils."""

from __future__ import annotations

from opencite.utils import (
    normalize_title,
    parse_author_name,
    reconstruct_abstract,
    titles_similar,
)


class TestNormalizeTitle:
    def test_basic(self):
        words = normalize_title("Attention Is All You Need")
        assert "attention" in words
        assert "need" in words
        # "is" and "all" are < 3 chars, excluded
        assert "is" not in words

    def test_unicode(self):
        words = normalize_title("Rene\u0301 Descartes' Method")
        assert "ren\u00e9" in words or "rene" in words

    def test_punctuation_removed(self):
        words = normalize_title("Brain-Computer Interfaces: A Review")
        assert "braincomputer" in words or "brain" in words


class TestTitlesSimilar:
    def test_identical(self):
        a = normalize_title("Attention Is All You Need")
        assert titles_similar(a, a)

    def test_similar(self):
        a = normalize_title("Attention Is All You Need")
        b = normalize_title("Attention is All We Need")
        assert titles_similar(a, b)

    def test_different(self):
        a = normalize_title("Attention Is All You Need")
        b = normalize_title("Deep Reinforcement Learning for Robotics")
        assert not titles_similar(a, b)

    def test_empty(self):
        assert not titles_similar(set(), {"word"})
        assert not titles_similar(set(), set())


class TestParseAuthorName:
    def test_comma_format(self):
        author = parse_author_name("Smith, Jane")
        assert author.family_name == "Smith"
        assert author.given_name == "Jane"

    def test_space_format(self):
        author = parse_author_name("Jane Smith")
        assert author.family_name == "Smith"
        assert author.given_name == "Jane"

    def test_single_name(self):
        author = parse_author_name("Smith")
        assert author.family_name == "Smith"
        assert author.given_name == ""

    def test_empty(self):
        author = parse_author_name("")
        assert author.name == "Unknown"

    def test_citation_name(self):
        author = parse_author_name("Smith, Jane")
        assert author.citation_name() == "Smith, J."


class TestReconstructAbstract:
    def test_basic(self):
        inverted = {"We": [0], "studied": [1], "the": [2], "brain": [3]}
        assert reconstruct_abstract(inverted) == "We studied the brain"

    def test_empty(self):
        assert reconstruct_abstract(None) == ""
        assert reconstruct_abstract({}) == ""

    def test_out_of_order(self):
        inverted = {"brain": [3], "the": [2], "studied": [1], "We": [0]}
        assert reconstruct_abstract(inverted) == "We studied the brain"

    def test_repeated_word(self):
        inverted = {"the": [0, 2], "cat": [1], "dog": [3]}
        assert reconstruct_abstract(inverted) == "the cat the dog"
