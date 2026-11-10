"""Load and lightly validate a study spec."""
from __future__ import annotations

from pathlib import Path

import yaml

REQUIRED_SECTIONS = ["study", "data", "eligibility", "intervention", "comparison", "windows", "outputs"]


def load_spec(path: str | Path) -> dict:
    spec = yaml.safe_load(Path(path).read_text())
    missing = [s for s in REQUIRED_SECTIONS if s not in spec]
    if missing:
        raise ValueError(f"Spec {path} is missing sections: {', '.join(missing)}")
    if spec["data"].get("model") != "tuva":
        raise ValueError("Only the Tuva data model is supported so far (data.model: tuva)")
    return spec
