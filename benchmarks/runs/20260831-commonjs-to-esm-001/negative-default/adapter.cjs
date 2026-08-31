const fs = require("fs");
const api = require(".");

const request = JSON.parse(fs.readFileSync(0, "utf8"));
const { action, args } = request.input;
try {
  const value = action === "default" ? api.default(...args) : api.add(...args);
  process.stdout.write(JSON.stringify({ status: "passed", observed: { ok: true, value } }));
} catch (error) {
  process.stdout.write(JSON.stringify({
    status: "passed",
    observed: { ok: false, error: { name: error.name, message: error.message } }
  }));
}
