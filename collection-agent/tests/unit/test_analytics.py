"""US1 analytics tools (T022): reconciliation, unknown buckets, duplicates,
ranking bases, rarity exclusions, value passthrough, zero-instance guard."""

from __future__ import annotations

import pytest

from collection_agent.agent import AgentSession
from collection_agent.models import Completeness
from collection_agent.tools.analytics import (
    AggregateArgs,
    TopNArgs,
    _NoArgs,
    make_analytics_tools,
)
from tests.conftest import make_snapshot


@pytest.fixture()
def tools(settings, store, complete_snapshot):
    store.save(complete_snapshot)
    return {t.name: t for t in make_analytics_tools(settings, store)}


def _run(tools, name, **kwargs):
    tool = tools[name]
    return tool.fn(AgentSession(), tool.params_model(**kwargs))


# --- aggregate_by ---------------------------------------------------------


def test_single_valued_distribution_reconciles(tools):
    res = _run(tools, "aggregate_by", attribute="country")
    total = res["total_records"]
    bucket_sum = sum(b["count"] for b in res["buckets"]) + res["unknown_bucket"]["count"]
    assert total == 5
    assert bucket_sum == total  # SC-002: 100% of records accounted for
    assert res["unknown_bucket"]["count"] == 1  # record 5 has no country
    assert res["unknown_bucket"]["label"] == "unknown country"


def test_multi_valued_counting_disclosed(tools):
    res = _run(tools, "aggregate_by", attribute="genre")
    assert "multi-valued" in res["counting_note"]
    electronic = next(b for b in res["buckets"] if b["value"] == "Electronic")
    assert electronic["count"] == 3  # records 1, 2, 4 (duplicate counts twice)
    assert res["unknown_bucket"]["count"] == 1  # record 5: no genres


def test_duplicate_instances_count(tools):
    res = _run(tools, "aggregate_by", attribute="decade")
    d2000 = next(b for b in res["buckets"] if b["value"] == "2000s")
    assert d2000["count"] == 2  # release 1 owned twice (instances 1 and 4)
    assert res["unit"].startswith("instances")


def test_spanish_alias_accepted(tools):
    res = _run(tools, "aggregate_by", attribute="género")
    assert res["attribute"] == "genre"


def test_unsupported_attribute_names_supported_list(tools):
    res = _run(tools, "aggregate_by", attribute="catno")
    assert res["error"] == "unsupported_attribute"
    assert "genre" in res["supported"]


# --- top_n ------------------------------------------------------------------


def test_top_rated_shows_votes_and_excludes_missing(tools):
    res = _run(tools, "top_n", basis="community_rating", n=3)
    assert res["items"][0]["community_rating_avg"] == 4.9  # Jazz Cat
    assert res["items"][0]["votes"] == 800
    assert res["excluded_missing_data"] == 1  # record 5: no rating
    assert "vote count" in res["basis"]


def test_most_expensive_ranked_desc(tools):
    res = _run(tools, "top_n", basis="most_expensive", n=3)
    prices = [i["lowest_price"] for i in res["items"]]
    assert prices == sorted(prices, reverse=True)
    assert res["items"][0]["lowest_price"] == 150.0
    assert "not an appraisal" in res["basis"]


def test_rarest_excludes_missing_stats_never_falsely_rare(tools):
    res = _run(tools, "top_n", basis="rarest", n=5)
    ids = [i["instance_id"] for i in res["items"]]
    assert 5 not in ids  # record 5 has no community stats → excluded, not "rare"
    assert res["excluded_missing_data"] >= 1
    # record 2: want/have 200/40=5.0 AND 0 for sale → very rare, ranked first
    assert res["items"][0]["instance_id"] == 2
    assert res["items"][0]["scarcity"] == "very rare"
    assert "want/have" in res["basis"]  # criterion stated (FR-008)


# --- collection_value ----------------------------------------------------------


def test_collection_value_verbatim_with_basis(tools):
    res = _run(tools, "collection_value")
    assert res["median"] == "US$250.00"  # Discogs string passthrough
    assert "estimate" in res["basis"]


# --- serving guard cases ----------------------------------------------------------


def test_partial_snapshot_carries_warning(settings, store, partial_snapshot):
    store.save(partial_snapshot)
    tools = {t.name: t for t in make_analytics_tools(settings, store)}
    res = _run(tools, "aggregate_by", attribute="genre")
    assert any("PARTIAL" in w for w in res["warnings"])


def test_no_snapshot_blocks_with_sync_required(settings, store):
    tools = {t.name: t for t in make_analytics_tools(settings, store)}
    res = _run(tools, "aggregate_by", attribute="genre")
    assert res["error"] == "sync_required"


def test_zero_instance_snapshot_blocks_explicitly(settings, store):
    store.save(make_snapshot([]))  # synced but empty — no div-by-zero, no 0% buckets
    tools = {t.name: t for t in make_analytics_tools(settings, store)}
    for name, kwargs in [
        ("aggregate_by", {"attribute": "genre"}),
        ("top_n", {"basis": "rarest"}),
        ("collection_value", {}),
    ]:
        res = _run(tools, name, **kwargs)
        assert res["error"] == "empty_collection", name
