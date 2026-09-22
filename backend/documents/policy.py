from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from django.conf import settings

from .categories import CATEGORY_ORDER


class PolicyError(ValueError):
    pass


VALID_MODES = {"mask", "redact", "keep"}


def load_policy(path: str | Path | None = None) -> dict:
    policy_path = Path(path or settings.REDACTION_POLICY_PATH)

    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"Policy file does not exist: {policy_path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"Policy file is invalid JSON: {exc}") from exc

    entities = policy.get("entities")

    if not isinstance(entities, dict):
        raise PolicyError("Policy must contain an entities object")

    for category, rule in entities.items():
        if category not in CATEGORY_ORDER:
            raise PolicyError(f"Unknown policy category: {category}")

        mode = rule.get("mode")

        if mode in {"pseudo", "pseudonymize"}:
            raise PolicyError(
                f"Pseudonymization is not available in the first release: "
                f"{category}"
            )

        if mode not in VALID_MODES:
            raise PolicyError(
                f"Invalid mode for {category}: {mode}"
            )

    return policy


def policy_snapshot(path: str | Path | None = None) -> dict:
    """Return an independent copy suitable for storing with a job."""
    return deepcopy(load_policy(path))