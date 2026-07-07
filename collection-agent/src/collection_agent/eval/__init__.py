"""Owner-run scan-identification eval (023). Imported lazily by cli.py only.

Read-only against Discogs by construction: nothing in this package may
reference the client's write methods or the scan journal/session (enforced
by tests/unit/test_eval_readonly_guard.py; contracts/eval-results.md §4).
"""
