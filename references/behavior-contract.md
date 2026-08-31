# Behavior Contract and Parity Corpus

The machine-readable contract is `migration.json`, not YAML. The current format is schema version 2 and uses only JSON so the deterministic helpers remain standard-library-only.

## Contract versus corpus

The Contract answers:

> Which observable behaviors must remain stable?

The Corpus answers:

> Which concrete inputs will exercise those behaviors?

Do not put expected output, comparison rules, or ad-hoc tolerances in the Corpus. Those belong to the Contract. The adapter describes how to start an implementation; the runner sends each Corpus case to the adapter.

## Contract shape

```json
{
  "schema_version": 2,
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
    "framework": "Express",
    "entrypoints": ["server.js"]
  },
  "environment": {
    "set": {"NODE_ENV": "test"}
  },
  "public_surfaces": [
    {
      "id": "public-http",
      "kind": "http",
      "required": true,
      "source_adapter": {
        "kind": "harness",
        "argv": ["python", "tests/parity/http_adapter.py"]
      },
      "target_adapter": {
        "kind": "harness",
        "argv": ["python", "tests/parity/http_adapter.py"]
      },
      "compare": {
        "fields": {
          "status": {"mode": "exact"},
          "body": {"mode": "json-semantic"}
        }
      },
      "evidence": ["app/routes.py", "tests/test_api.py"],
      "confidence": "high",
      "operations": [
        {
          "id": "GET-/health",
          "required": true,
          "evidence": [
            {"path": "app/routes.py", "type": "route-definition", "line": 12},
            {"path": "tests/test_api.py", "type": "existing-test"}
          ]
        }
      ]
    }
  ],
  "completion_gates": {
    "required_check_kinds": ["test"]
  },
  "checks": {
    "source": [],
    "target": []
  },
  "parity_corpus": "parity-corpus.json"
}
```

Every v2 required operation needs non-empty evidence. Evidence may be a repository-relative path or an object with `path`, `type`, and an optional positive `line`. This makes Codex's operation enumeration auditable without requiring a parser for every framework.

Supported public surface kinds are `command`, `http`, `library`, `snapshot`, and `file-io`. Each surface has a portable Source adapter and Target adapter. Both adapters must use an explicit argv array; shell strings and `shell: true` are rejected.

## Environment policy

Checks and adapters receive a minimal environment by default. The host environment is not copied wholesale. A Contract may explicitly declare non-secret names to inherit or values to set:

```json
{
  "environment": {
    "inherit": ["NODE_ENV"],
    "set": {"LANG": "C.UTF-8"}
  }
}
```

Names that look like keys, tokens, passwords, credentials, or private keys are rejected. A real integration test that needs a secret must use an authorized external sandbox and must not put the secret in the Contract, logs, or results.

## Checks

```json
{
  "id": "unit-tests",
  "kind": "test",
  "argv": ["python", "-m", "unittest"],
  "cwd": ".",
  "timeout_seconds": 300,
  "expected_exit_code": 0,
  "required": true
}
```

Only configured required check kinds are completion gates. For example, a small CLI may require `test` and `parity` without inventing a separate build/static command. Individual checks marked `required: true` still have to pass.

## Corpus shape

```json
{
  "schema_version": 2,
  "cases": [
    {
      "id": "health",
      "surface_id": "public-http",
      "operation_id": "GET-/health",
      "input": {
        "method": "GET",
        "path": "/health"
      },
      "required": true
    }
  ]
}
```

The same case is sent to Source and Target by `scripts/run_parity.py`. An adapter receives:

```json
{
  "case_id": "health",
  "surface_id": "public-http",
  "operation_id": "GET-/health",
  "input": {"method": "GET", "path": "/health"}
}
```

It must emit one JSON object on stdout with `status: "passed"` and an `observed` value. The `observed` value is compared by the frozen surface comparator.

## Comparison modes

Schema v2 uses one unambiguous comparator shape:

```json
{"whole": {"mode": "json-semantic"}}
```

or:

```json
{
  "fields": {
    "status": {"mode": "exact"},
    "body": {
      "mode": "text-normalized",
      "normalization": ["crlf-to-lf", "trim-trailing-whitespace"]
    }
  }
}
```

Supported modes are `exact`, `text`, `text-normalized`, `json-semantic`, `exit-code`, and `snapshot`. JSON semantic comparison ignores object key order but does not ignore missing fields, changed types, or `null` versus absent. Normalization is explicit and is applied by the comparator, not merely recorded in the contract.

Schema v1 remains readable for compatibility, but its surface-only coverage cannot establish a fully verified v2 migration. New contracts should use schema v2.

## Freeze rule

First run the positive Source Judge, then run targeted negative controls against deliberately mutated required cases. `scripts/validate_judge.py` produces the only accepted Judge artifact. `scripts/freeze_contract.py` then freezes the Source revision/tree digest, Contract, Corpus, Judge artifact, check specification, normalization policy, and every Python file in the verifier bundle.

After Freeze, do not remove a required case or operation, lower its required flag, widen a comparator, or edit verifier code to make a migration pass. Revalidate and create a new Freeze only after explicit approval.
