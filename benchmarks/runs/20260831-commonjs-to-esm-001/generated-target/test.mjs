import assert from "node:assert/strict";
import greet, { add } from "migration-skill-cjs-case";

assert.strictEqual(greet("Ada"), "hello Ada");
assert.strictEqual(greet("张三"), "hello 张三");
assert.strictEqual(add(2, 3), 5);
assert.strictEqual(add(-2, 5.5), 3.5);
assert.throws(() => greet(""), {name: "TypeError", message: "name required"});
assert.throws(() => greet(null), {name: "TypeError", message: "name required"});
assert.throws(() => add(2, "3"), {name: "TypeError", message: "numbers required"});
console.log("esm ok");
