# Behavior Contract and Parity Corpus

The machine-readable contract is `migration.json`, not YAML. It uses ordinary JSON so the helper scripts remain standard-library-only.

## Contract shape

```json
{
  "schema_version": 1,
  "source": {
    "root": ".",
    "revision": "AUTO",
    "language": "Python",
    "framework": "Flask",
    "entrypoints": ["app.py"]
  },
  "target": {
    "root": "../target",
    "language": "Node.js",
    "framework": "Express"
  },
  "public_surfaces": [
    {
      "id": "main-http",
      "kind": "http",
      "description": "Health endpoint",
      "required": true,
      "source_adapter": {
        "kind": "harness",
        "argv": ["python", "tests/parity/http_adapter.py", "--implementation", "source"]
      },
      "target_adapter": {
        "kind": "harness",
        "argv": ["python", "tests/parity/http_adapter.py", "--implementation", "target"]
      },
      "compare": {"status": true, "body": "json-semantic"},
      "evidence": ["tests/test_api.py"],
      "confidence": "high"
    }
  ],
  "checks": {
    "source": [],
    "target": []
  },
  "parity_corpus": "parity-corpus.json"
}
```

Required top-level fields are `schema_version`, `source`, `target`, `public_surfaces`, and `parity_corpus`. `checks` may be a single list or an object with `source` and `target` lists.

Each check has:

```json
    {
      "id": "unit-tests",
      "kind": "test",
      "argv": ["python", "-m", "unittest"],
      "cwd": ".",
      "env": {},
      "timeout_seconds": 300,
      "expected_exit_code": 0,
      "required": true
}
```

Commands are argv arrays. Do not use implicit shell strings. Environment values are never written to result files; do not put secrets in the command or contract.

## Corpus shape

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "health-ok",
      "surface_id": "main-http",
      "input": {
        "method": "GET",
        "path": "/health"
      },
      "required": true
    }
  ]
}
```

Supported surface kinds are `command`, `http`, `library`, `snapshot`, and `file-io`. The corpus describes inputs only; the adapter or harness describes how to execute them and returns case records such as:

```json
{
  "cases": [
    {
      "id": "health-ok",
      "surface_id": "main-http",
      "status": "passed",
      "observed": {"status": 200, "body": {"ok": true}}
    }
  ]
}
```

Do not put expected output, comparison rules, or normalization rules in the corpus. Those belong to the Contract and its freeze manifest.

Supported comparison modes are `exact`, `text-normalized`, `json-semantic`, `exit-code`, and `snapshot`. A `true` comparator means `exact`. JSON semantic comparison ignores object key order but does not ignore missing fields, changed types, or `null` versus absent.

## Freeze rule

After the source positive-control and mutation negative-control runs pass, freeze the contract, corpus, evaluator, check specification, and source revision. If any frozen asset changes, rerun validation and freeze instead of silently continuing.
