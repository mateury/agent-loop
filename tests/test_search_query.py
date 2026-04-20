"""Unit tests for agent_loop.search.query."""

import pytest
from agent_loop.search.query import sanitize_fts5_query, has_cjk


class TestSanitizeFts5Query:
    def test_empty_returns_empty(self):
        assert sanitize_fts5_query("") == ""
        assert sanitize_fts5_query(None) == ""

    def test_simple_query_passthrough(self):
        assert sanitize_fts5_query("hello world") == "hello world"

    def test_strips_special_chars(self):
        result = sanitize_fts5_query("hello+world{test}")
        assert "+" not in result
        assert "{" not in result
        assert "}" not in result

    def test_preserves_quoted_phrases(self):
        result = sanitize_fts5_query('"exact phrase"')
        assert '"exact phrase"' in result

    def test_unbalanced_quote_stripped(self):
        result = sanitize_fts5_query('hello "world')
        # unbalanced quote treated as special char, stripped
        assert result == "hello world"

    def test_boolean_operators_uppercase(self):
        result = sanitize_fts5_query("foo AND bar")
        assert "AND" in result

    def test_boolean_operators_case_preserved(self):
        result = sanitize_fts5_query("cat OR dog")
        assert "OR" in result

    def test_dangling_operator_stripped(self):
        result = sanitize_fts5_query("AND hello OR")
        assert not result.startswith("AND")
        assert not result.endswith("OR")
        assert "hello" in result

    def test_hyphenated_token_quoted(self):
        result = sanitize_fts5_query("chat-send")
        assert '"chat-send"' in result

    def test_dotted_token_quoted(self):
        result = sanitize_fts5_query("flask.app")
        assert '"flask.app"' in result

    def test_collapses_multiple_stars(self):
        result = sanitize_fts5_query("hel***lo")
        assert "***" not in result

    def test_wildcard_single_star(self):
        result = sanitize_fts5_query("hel*lo")
        assert "hel*lo" in result

    def test_nonsense_chars_stripped(self):
        result = sanitize_fts5_query("foo@bar#baz")
        assert "@" not in result
        assert "#" not in result


class TestHasCjk:
    def test_ascii_returns_false(self):
        assert has_cjk("hello world") is False
        assert has_cjk("") is False

    def test_chinese_returns_true(self):
        assert has_cjk("你好世界") is True

    def test_japanese_hiragana_returns_true(self):
        assert has_cjk("こんにちは") is True

    def test_japanese_katakana_returns_true(self):
        assert has_cjk("コンニチハ") is True

    def test_korean_returns_true(self):
        assert has_cjk("안녕하세요") is True

    def test_mixed_ascii_cjk_returns_true(self):
        assert has_cjk("hello 世界") is True

    def test_emoji_returns_false(self):
        # Emoji are not CJK
        assert has_cjk("hello 🌍") is False
