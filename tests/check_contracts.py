"""Standalone producer/consumer contract check used by CI and local agents."""

import sys
from importlib import import_module
from pathlib import Path

import yaml


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    validate_config = import_module("src.onramp.engine").validate_config
    validate_value_map_targets = import_module(
        "src.onramp.config_contract"
    ).validate_value_map_targets
    validate_proposal = import_module("src.onramp.validate_proposal").validate_proposal
    model = yaml.safe_load((root / "model" / "model.yml").read_text(encoding="utf-8"))
    errors = []
    founding_sources = []
    proposal_paths = {
        path.name.removesuffix(".proposal.yml"): path
        for path in sorted((root / "src" / "onramp" / "proposals").glob("*.proposal.yml"))
    }
    for path in sorted((root / "src" / "onramp" / "sources").glob("*.yml")):
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(config, dict) and config.get("origination", "steward_only") == "founding":
            founding_sources.append(str(config.get("source")))
        errors.extend(f"{path}: {error}" for error in validate_config(config, model))
        target_result = validate_value_map_targets(config, model, root / "spec" / "rdl")
        source = config.get("source") if isinstance(config, dict) else None
        proposal_path = proposal_paths.pop(source, None)
        if proposal_path is not None:
            errors.extend(
                f"{proposal_path}: {error}"
                for error in validate_proposal(proposal_path, path, root)
            )
        elif target_result.warnings:
            keys = ", ".join(sorted(warning.key for warning in target_result.warnings))
            errors.append(
                f"{path}: unverifiable value_maps need a proposal acknowledgement: {keys}"
            )
    for source, proposal_path in proposal_paths.items():
        errors.append(f"{proposal_path}: no candidate source YAML for {source}")
    if len(founding_sources) != 1:
        errors.append(
            "exactly one committed source must declare origination: founding; found "
            + repr(sorted(founding_sources))
        )
    if errors:
        print("\n".join(errors))
        return 1
    print("all source configuration and mapping-proposal contracts are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
