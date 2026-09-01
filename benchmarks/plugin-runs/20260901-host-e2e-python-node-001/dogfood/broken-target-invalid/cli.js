#!/usr/bin/env node

function emit(value, outputFormat) {
  if (outputFormat === "text") {
    process.stdout.write(typeof value === "string" ? value + "\n" : JSON.stringify(value) + "\n");
  } else {
    process.stdout.write(JSON.stringify(value) + "\n");
  }
  return 0;
}

function main(argv) {
  let name = null;
  let outputFormat = "json";
  let uppercase = false;
  let index = 0;

  while (index < argv.length) {
    const option = argv[index];
    if (option === "--name") {
      if (index + 1 >= argv.length) {
        console.log(JSON.stringify({ error: "name required" }));
        return 2;
      }
      name = argv[index + 1];
      index += 2;
      continue;
    }
    if (option === "--format") {
      if (index + 1 >= argv.length || !["json", "text"].includes(argv[index + 1])) {
        console.log(JSON.stringify({ error: "format must be json or text" }));
        return 2;
      }
      outputFormat = argv[index + 1];
      index += 2;
      continue;
    }
    if (option === "--uppercase") {
      uppercase = true;
      index += 1;
      continue;
    }
    console.log(JSON.stringify({ error: "invalid arguments" }));
    return 0;
  }

  if (name === null || name.length === 0) {
    console.log(JSON.stringify({ error: "name required" }));
    return 2;
  }

  const displayedName = uppercase ? name.toUpperCase() : name;
  const greeting = "hello " + displayedName;
  return outputFormat === "json" ? emit({ greeting }, outputFormat) : emit(greeting, outputFormat);
}

process.exitCode = main(process.argv.slice(2));
