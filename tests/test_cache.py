"""Tests for the schema cache."""

import time

from queryadapter.cache import SchemaCache


def test_cache_stores_and_returns():
    cache = SchemaCache(ttl=60)
    assert cache.get_collections() is None
    cache.set_collections({"t": {"c"}})
    assert cache.get_collections() == {"t": {"c"}}


def test_cache_ttl_expiry():
    cache = SchemaCache(ttl=0)
    cache.set_collections({"t": {"c"}})
    assert cache.get_collections() is None


def test_cache_invalidate():
    cache = SchemaCache(ttl=60)
    cache.set_collections({"t": {"c"}})
    cache.set_ddl("CREATE TABLE t")
    cache.invalidate()
    assert cache.get_collections() is None
    assert cache.get_ddl() is None
