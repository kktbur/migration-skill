"use strict";

function emit(value, format) {
  if (format === "text") {
    process.stdout.write(`${value}\n`);
  } else {
    process.stdout.write(`${JSON.stringify(value)}\n`);
  }
}

function main(argv) {
  let name = null;
  let format = "json";
  let uppercase = false;
  for (let index = 0; index < argv.length; index += 1) {
    const option = argv[index];
    if (option === "--name" && index + 1 < argv.length) {
      name = argv[index + 1];
      index += 1;
    } else if (option === "--name") {
      emit({error: "name required"}, "json");
      return 2;
    } else if (option === "--format" && index + 1 < argv.length) {
      format = argv[index + 1];
      index += 1;
    } else if (option === "--format") {
      emit({error: "format must be json or text"}, "json");
      return 2;
    } else if (option === "--uppercase") {
      uppercase = true;
    } else {
      emit({error: "invalid arguments"}, "json");
      return 2;
    }
  }
  if (name === null || name.length === 0) {
    emit({error: "name required"}, "json");
    return 2;
  }
  if (format !== "json" && format !== "text") {
    emit({error: "format must be json or text"}, "json");
    return 2;
  }
  if (format === "text") {
    emit(`hello ${uppercase ? name.toUpperCase() : name}`, format);
  } else {
    emit({greeting: `hello ${uppercase ? name.toUpperCase() : name}`}, "json");
  }
  return 0;
}

process.exitCode = main(process.argv.slice(2));
