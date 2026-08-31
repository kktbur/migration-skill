# Blind benchmark: Flask → FastAPI

This case specification follows the first cross-language benchmark. It contains a small Flask Source, its public behavior Contract, a separate parity Corpus, and a bounded migration plan. It intentionally contains no FastAPI Target or reference implementation.

The public operations are `GET-/health`, `GET-/users/:id`, and `POST-/users`. Cases cover successful responses, a missing user, invalid input, and an empty name. The adapters use Flask's test client so the benchmark does not need a listening server; an actual run must provide the declared dependency inside an approved execution environment.

This case is a specification only. Do not claim `VERIFIED` until a dated run under `benchmarks/runs/` contains a generated FastAPI Target, a frozen Judge, accepted milestones, and a broken-Target rejection.
