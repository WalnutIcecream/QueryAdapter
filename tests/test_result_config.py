"""Tests for the result object and configuration models."""

from queryadapter import Result, QueryAdapterConfig


def test_result_defaults():
    r = Result()
    assert r.data is None
    assert r.columns == []
    assert len(r) == 0


def test_result_len_and_iter():
    r = Result(data=[{"a": 1}, {"a": 2}])
    assert len(r) == 2
    assert list(r) == [{"a": 1}, {"a": 2}]


def test_result_to_dict():
    r = Result(data=[1], columns=["n"], database="sqlite", row_count=1)
    d = r.to_dict()
    assert d["data"] == [1]
    assert d["columns"] == ["n"]
    assert d["row_count"] == 1


def test_config_defaults():
    c = QueryAdapterConfig()
    assert c.read_only is True
    assert c.provider == "ollama"
    assert c.cache_ttl == 300
    assert c.max_limit == 1000


def test_config_to_dict():
    c = QueryAdapterConfig(db_type="mongodb", provider="openai")
    d = c.to_dict()
    assert d["db_type"] == "mongodb"
    assert d["provider"] == "openai"
