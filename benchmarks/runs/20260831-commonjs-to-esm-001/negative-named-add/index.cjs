function greet(name) {
  if (typeof name !== "string" || name.length === 0) {
    throw new TypeError("name required");
  }
  return `hello ${name}`;
}

function add(left, right) {
  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError("numbers required");
  }
  return left + right + 1;
}

module.exports = { default: greet, add };
