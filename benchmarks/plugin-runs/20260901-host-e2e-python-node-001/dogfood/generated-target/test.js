const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");

function run(...args) {
  return spawnSync(process.execPath, ["cli.js", ...args], {
    encoding: "utf8",
  });
}

const normal = run("--name", "Ada");
assert.equal(normal.status, 0);
assert.deepEqual(JSON.parse(normal.stdout), { greeting: "hello Ada" });

const text = run("--name", "Ada", "--format", "text");
assert.equal(text.status, 0);
assert.equal(text.stdout.trim(), "hello Ada");

const empty = run("--name", "");
assert.equal(empty.status, 2);

const invalid = run("--unknown");
assert.equal(invalid.status, 2);

const unicode = run("--name", "张三");
assert.deepEqual(JSON.parse(unicode.stdout), { greeting: "hello 张三" });

const uppercase = run("--name", "Ada", "--uppercase");
assert.deepEqual(JSON.parse(uppercase.stdout), { greeting: "hello ADA" });

console.log("target tests passed");
