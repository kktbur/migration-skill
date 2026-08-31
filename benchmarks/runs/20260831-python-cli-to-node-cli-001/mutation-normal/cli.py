"""Small source CLI used by the blind Python-to-Node benchmark."""

from __future__ import annotations

import json
import sys


def _emit(value: object, output_format: str) -> int:
    if output_format == "text":
        print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str]) -> int:
    name: str | None = None
    output_format = "json"
    uppercase = False
    index = 0
    while index < len(argv):
        option = argv[index]
        if option == "--name":
            if index + 1 >= len(argv):
                print(json.dumps({"error": "name required"}, ensure_ascii=False, sort_keys=True))
                return 2
            name = argv[index + 1]
            index += 2
            continue
        if option == "--format":
            if index + 1 >= len(argv) or argv[index + 1] not in {"json", "text"}:
                print(json.dumps({"error": "format must be json or text"}, sort_keys=True))
                return 2
            output_format = argv[index + 1]
            index += 2
            continue
        if option == "--uppercase":
            uppercase = True
            index += 1
            continue
        print(json.dumps({"error": "invalid arguments"}, sort_keys=True))
        return 2
    if name is None or not name:
        print(json.dumps({"error": "name required"}, ensure_ascii=False, sort_keys=True))
        return 2
    displayed_name = name.upper() if uppercase else name
    greeting = "goodbye " + displayed_name
    return _emit({"greeting": greeting}, output_format) if output_format == "json" else _emit(greeting, output_format)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
