"""Plan retention cleanup; --apply explicitly removes eligible old data."""

import argparse
import json
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from api.lifecycle import purge_data
from api.runtime import Runtime
from api.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    runtime = Runtime(Settings.from_env())
    try:
        print(json.dumps(purge_data(runtime, apply=args.apply)))
    finally:
        runtime.db.close()


if __name__ == "__main__":
    main()
