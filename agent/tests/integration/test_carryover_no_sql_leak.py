"""US4 / T100 — carry-over carries text only.

Submit two queries on the same thread. The second run's
``metadata.carryover.preamble`` must NOT contain any of the first
run's generated SQL or generated Python — only the prior
``user_query`` text. Encodes the "light contextual carry-over"
boundary from R-04.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_carryover_omits_sql_and_code(agent_env: dict) -> None:
    QR = agent_env["QueryRequest"]
    post = agent_env["post_query"]

    r1 = post(QR(message="Show the evolution of Techno releases over time"))
    assert r1.status == "succeeded"
    assert r1.sql is not None and r1.sql.strip()

    # Pull the first run's persisted code (admin path) so we know
    # exactly what we don't want leaking into r2's carry-over.
    from discogs_agent.api import app
    from discogs_agent.config import settings

    settings.AGENT_ADMIN_TOKEN = "leak-test-token"

    with TestClient(app) as client:
        r1_full = client.get(
            f"/runs/{r1.run_id}",
            headers={"X-Agent-Admin": "leak-test-token"},
        ).json()

    r1_sql = r1_full["generated_sql"] or ""
    r1_code = r1_full["generated_code"] or ""
    assert r1_sql, "first run should have persisted SQL"
    assert r1_code, "first run should have persisted code"

    r2 = post(
        QR(
            message="Show the evolution of House releases over time",
            thread_id=r1.thread_id,
        )
    )
    assert r2.status == "succeeded"

    with TestClient(app) as client:
        r2_full = client.get(f"/runs/{r2.run_id}").json()

    carryover = r2_full["metadata"]["carryover"]
    assert carryover is not None
    preamble = carryover["preamble"] or ""

    # The preamble must contain the prior user_query text.
    assert "Techno releases over time" in preamble

    # And must NOT contain any of the prior run's SQL or code.
    # (Pick distinctive substrings — the SELECT keyword alone would
    # false-positive on "Show ... selected" tokens.)
    forbidden_sql_substrings = [
        "release_unique_view",
        "release_fact",
        "GROUP BY",
        "COUNT(DISTINCT",
        "FROM",
    ]
    for needle in forbidden_sql_substrings:
        assert needle not in preamble, f"SQL leaked into carryover: {needle!r}"

    forbidden_code_substrings = [
        "import duckdb",
        "import pandas",
        "plotly",
        "duckdb.connect",
        "fig.write_html",
    ]
    for needle in forbidden_code_substrings:
        assert needle not in preamble, f"code leaked into carryover: {needle!r}"
