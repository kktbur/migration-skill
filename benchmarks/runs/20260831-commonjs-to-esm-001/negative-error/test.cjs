const assert = require("assert");
const api = require(".");

assert.strictEqual(api.default("Ada"), "hello Ada");
assert.strictEqual(api.default("张三"), "hello 张三");
assert.strictEqual(api.add(2, 3), 5);
assert.strictEqual(api.add(-2, 5.5), 3.5);
assert.throws(() => api.default(""), {name: "TypeError", message: "name required"});
assert.throws(() => api.default(null), {name: "TypeError", message: "name required"});
assert.throws(() => api.add(2, "3"), {name: "TypeError", message: "numbers required"});
console.log("ok");
