"""
FlowStrix Schema Parser — Load and validate agent YAML specs.

Uses Pydantic for strict validation with clear error messages.
This is the "compiler frontend" — YAML in, typed AgentSpec out.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from flowstrix.schema.models import AgentSpec


class SchemaParseError(Exception):
    """Raised when a YAML file fails schema validation."""

    def __init__(self, errors: list[dict], source: str | None = None):
        self.errors = errors
        self.source = source
        error_summary = "\n".join(
            f"  - {e['loc']}: {e['msg']}" for e in errors[:10]
        )
        super().__init__(
            f"Schema validation failed{f' ({source})' if source else ''}:\n{error_summary}"
        )


def parse_yaml(path: str | Path) -> AgentSpec:
    """Parse a YAML file into a validated AgentSpec.

    Args:
        path: Path to the YAML agent definition file.

    Returns:
        Validated AgentSpec object.

    Raises:
        SchemaParseError: If the YAML doesn't conform to the schema.
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Agent spec not found: {path}")

    raw = yaml.safe_load(path.read_text())

    if raw is None:
        raise SchemaParseError(
            [{"loc": ("root",), "msg": "Empty YAML file"}], source=str(path)
        )

    try:
        return AgentSpec.model_validate(raw)
    except ValidationError as e:
        raise SchemaParseError(e.errors(), source=str(path)) from e


def parse_yaml_string(content: str) -> AgentSpec:
    """Parse a YAML string into a validated AgentSpec.

    Useful for testing and for the Ghostwriter compiler output.
    """
    raw = yaml.safe_load(content)

    if raw is None:
        raise SchemaParseError([{"loc": ("root",), "msg": "Empty YAML content"}])

    try:
        return AgentSpec.model_validate(raw)
    except ValidationError as e:
        raise SchemaParseError(e.errors()) from e
