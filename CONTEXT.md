# Migration Skill domain glossary

This glossary defines the protocol vocabulary used by the repository. It is
intentionally independent of a programming language, framework, or Codex host.

| Term | Meaning |
| --- | --- |
| Behavior Contract | The obligations a migrated implementation must preserve at a public boundary. It names surfaces and atomic operations; it is not a list of test inputs. |
| Operation | One externally observable behavior that can be evidenced and accepted independently, such as a route, command, export, or file interaction. |
| Parity Corpus | Concrete inputs used to exercise Contract operations. It proves selected behavior; it does not define how an implementation starts. |
| Judge | The adapters, comparators, required cases, and evaluator that decide whether Source and Target observations satisfy the Contract. |
| Freeze | The integrity boundary that binds Source evidence, Contract, Corpus, Judge rules, and verifier files to recorded digests. |
| Milestone | A bounded, reversible change whose acceptance is determined by the verification ratchet. |
| Checkpoint | The accepted state of a Target after a milestone passes its required gates. |
| Strangler migration | An operation-by-operation coexistence plan in which old and new implementations are compared locally before an old operation is retired. It is not an automatic production traffic switch. |
| Migration shard | A monorepo subset with a defined package boundary, dependency boundary, and verification scope. |
| Verification ratchet | The rule that an accepted checkpoint cannot be replaced by a result that fails required gates or regresses previously accepted evidence. |

The Source remains the executable specification until the final required
operations are verified. A score or percentage can summarize evidence, but it
cannot replace a required operation, case, or gate.
