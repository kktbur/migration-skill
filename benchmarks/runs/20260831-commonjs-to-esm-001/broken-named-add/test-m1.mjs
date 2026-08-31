import assert from "node:assert/strict";
import greet from "migration-skill-cjs-case";

assert.strictEqual(greet("Ada"), "hello Ada");
assert.strictEqual(greet("张三"), "hello 张三");
console.log("m1 ok");
