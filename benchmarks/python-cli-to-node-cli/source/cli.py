import json
import sys


def main(argv):
    if len(argv) == 2 and argv[0] == "--name":
        if not argv[1]:
            print(json.dumps({"error": "name required"}, sort_keys=True))
            return 2
        print(json.dumps({"greeting": "hello " + argv[1]}, sort_keys=True))
        return 0
    print(json.dumps({"error": "invalid arguments"}, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
