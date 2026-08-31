import assert from "node:assert/strict";
import greet, { add } from "migration-skill-cjs-case";

assert.strictEqual(greet("Ada"), "hello Ada");
assert.strictEqual(add(2, 3), 5);
assert.strictEqual(add(-2, 5.5), 3.5);
console.log("m2 ok");
