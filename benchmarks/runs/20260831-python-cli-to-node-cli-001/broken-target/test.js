"use strict";

const assert = require("assert");
const {spawnSync} = require("child_process");

function run(...args) {
  return spawnSync(process.execPath, ["cli.js", ...args], {cwd: __dirname, encoding: "utf8"});
}

const json = run("--name", "Ada");
assert.strictEqual(json.status, 0);
assert.deepStrictEqual(JSON.parse(json.stdout), {greeting: "hello Ada"});

const text = run("--name", "Ada", "--format", "text");
assert.strictEqual(text.status, 0);
assert.strictEqual(text.stdout.trim(), "hello Ada");

function assertError(result, message) {
  assert.strictEqual(result.status, 2);
  assert.deepStrictEqual(JSON.parse(result.stdout), {error: message});
}

assertError(run("--unknown"), "invalid arguments");
assertError(run("--name"), "name required");
assertError(run("--name", "Ada", "--format", "xml"), "format must be json or text");
assertError(run("--name", ""), "name required");

const unicode = run("--name", "张三");
assert.strictEqual(unicode.status, 0);
assert.deepStrictEqual(JSON.parse(unicode.stdout), {greeting: "hello 张三"});

const uppercase = run("--name", "Ada", "--uppercase");
assert.strictEqual(uppercase.status, 0);
assert.deepStrictEqual(JSON.parse(uppercase.stdout), {greeting: "hello ADA"});

console.log("ok");
