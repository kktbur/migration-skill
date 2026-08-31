const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const root = __dirname;

function runCli(...args) {
  const result = spawnSync("node", [path.join(root, "cli.js"), ...args], { encoding: "utf8" });
  return { code: result.status, output: JSON.parse(result.stdout) };
}

assert.deepEqual(runCli("--name", "Ada"), { code: 0, output: { greeting: "hello Ada" } });
assert.deepEqual(runCli("--name", ""), { code: 2, output: { error: "name required" } });
assert.deepEqual(runCli("--unknown"), { code: 2, output: { error: "invalid arguments" } });
