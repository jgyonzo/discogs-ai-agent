// MSW handlers for the agent HTTP API. Used by component and integration tests.
// The success/failure shapes match contracts/api-consumption.md and the source
// of truth at specs/004-agent-v1/contracts/api.md.

import { http, HttpResponse } from "msw";
import { makeQueryResponse } from "./factories";

const BASE_URL = "http://localhost:8000";

const PLOTLY_STUB_HTML =
  "<!doctype html><html><head><title>Chart</title></head><body><div id='chart'>stub-chart</div><script>/* plotly stub */</script></body></html>";

export const handlers = [
  // POST /query — happy path. Per-test handlers can override via server.use(...).
  http.post(`${BASE_URL}/query`, async () => {
    return HttpResponse.json(makeQueryResponse());
  }),

  // GET /artifacts/:artifact_id — returns a tiny self-contained HTML stub.
  http.get(`${BASE_URL}/artifacts/:artifact_id`, () => {
    return new HttpResponse(PLOTLY_STUB_HTML, {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }),

  // GET /health — always green by default.
  http.get(`${BASE_URL}/health`, () => {
    return HttpResponse.json({
      status: "ok",
      checks: {
        duckdb: { ok: true, error: null },
        postgres: { ok: true, error: null },
      },
      version: "test",
      model_provider: "openai",
    });
  }),
];

export { PLOTLY_STUB_HTML };
