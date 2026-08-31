# Blind benchmark: Flask → FastAPI

This is a blind, source-only benchmark specification. It contains a small
Flask Source, its public behavior Contract, a separate parity Corpus, a
mutation plan, and a three-milestone migration plan. It intentionally contains
no FastAPI Target or reference implementation.

The Contract declares five atomic HTTP operations:

- `GET-/health`
- `GET-/users/:id`
- `POST-/users`
- `DELETE-/users/:id`
- `GET-/search`

The 21 required Corpus cases cover successful responses, missing and invalid
paths, query validation, Unicode search, JSON parsing, null and invalid fields,
duplicate names, and an empty `204` delete response. The behavior proof includes
status codes, JSON semantics, response content type, and route paths.

The adapters use the framework test clients rather than a listening server.
An actual run must provide Flask and FastAPI inside an approved isolated
execution environment. FastAPI's default validation behavior must be
explicitly controlled when it would otherwise produce a `422` response instead
of the frozen Flask `400` contract.

Do not claim `VERIFIED` until a dated run under `benchmarks/runs/` contains:

1. a generated FastAPI Target that is not copied from the Source;
2. a positive and mutation-tested Frozen Judge;
3. three accepted bounded milestones;
4. final required parity;
5. broken-Target rejection for status, validation, and response-field changes.
