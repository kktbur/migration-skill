const assert = require("assert");
const api = require(".");

assert.strictEqual(api.default("Ada"), "hello Ada");
assert.strictEqual(api.add(2, 3), 5);
assert.throws(() => api.default(""), {name: "TypeError", message: "name required"});
assert.throws(() => api.add(2, "3"), {name: "TypeError", message: "numbers required"});
console.log("ok");
