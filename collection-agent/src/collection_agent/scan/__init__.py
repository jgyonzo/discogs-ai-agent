"""Phone record scan (022): LAN HTTP server that turns a phone photo of a
physical record into an owner-confirmed add-to-collection on Discogs.

Pipeline: photo -> vision evidence (OpenAI, settings-driven model) ->
Discogs /database/search precision ladder -> candidates with duplicate
status -> explicit owner confirmation -> live add via DiscogsClient ->
snapshot marked stale + append-only session journal.
"""
