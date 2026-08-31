function main(argv) {
  if (argv.length === 2 && argv[0] === "--name") {
    if (!argv[1]) {
      process.stdout.write(JSON.stringify({ error: "name required" }) + "\n");
      return 2;
    }
    process.stdout.write(JSON.stringify({ greeting: "hello " + argv[1] }) + "\n");
    return 0;
  }
  process.stdout.write(JSON.stringify({ error: "invalid arguments" }) + "\n");
  return 2;
}

process.exitCode = main(process.argv.slice(2));
