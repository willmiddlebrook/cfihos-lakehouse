"""Standalone producer/consumer contract check used by CI and local agents."""

import sys
from importlib import import_module
from pathlib import Path

import yaml


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    validate_config = import_module("src.onramp.engine").validate_config
    model = yaml.safe_load((root / "model" / "model.yml").read_text(encoding="utf-8"))
    errors = []
    for path in sorted((root / "src" / "onramp" / "sources").glob("*.yml")):
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors.extend(f"{path}: {error}" for error in validate_config(config, model))
    if errors:
        print("\n".join(errors))
        return 1
    print("all source configuration producer/consumer contracts are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
