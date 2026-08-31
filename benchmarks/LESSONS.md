# Benchmark lessons

This file records repeatable protocol lessons discovered by the public
benchmarks. It is evidence for future benchmark design, not a replacement for
the frozen artifacts in each run.

## Flask → FastAPI

1. Framework defaults are observable behavior. Flask and FastAPI did not agree
   on the default response behavior for an empty `204`; the Contract therefore
   compares status, body, and content type.
2. FastAPI request validation defaults can produce `422`. The target had to
   parse the JSON body explicitly to preserve the source's `400` validation
   contract.
3. A parity adapter protocol must be encoding-safe on Windows. ASCII-safe JSON
   on stdin/stdout preserved a Unicode query and response while keeping the
   semantic values Unicode after decoding.
4. Negative controls should mutate one required operation at a time. Status,
   validation, and response-field mutations each mapped to an explicit case,
   so a random mismatch could not be counted as Judge success.

## Protocol follow-up

The next benchmark is CommonJS → ESM. It should specifically record module
entrypoint resolution, package export conditions, and runtime error behavior.
No CommonJS → ESM `VERIFIED` claim is made until its own dated run has the
same complete artifact chain.
