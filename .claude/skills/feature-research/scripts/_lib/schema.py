"""JSON Schema loading and validation with a shared registry (requires jsonschema)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from . import paths

BASE = "https://feature-research.local/schemas/"


@lru_cache(maxsize=None)
def _registry(schemas_dir: str) -> Registry:
    resources = []
    for f in sorted(Path(schemas_dir).glob("*.schema.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        resources.append((doc.get("$id", BASE + f.name), Resource.from_contents(doc)))
        resources.append((f.name, Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def schema_name(name: str) -> str:
    name = Path(name).name
    if name.endswith(".schema.json"):
        return name
    if name.endswith(".json"):
        name = name[: -len(".json")]
    return name + ".schema.json"


@lru_cache(maxsize=None)
def validator(name: str, schemas_dir: str | None = None) -> Draft202012Validator:
    sdir = schemas_dir or str(paths.SKILL_DIR / "schemas")
    path = Path(sdir) / schema_name(name)
    if not path.exists():
        raise FileNotFoundError(f"unknown schema {name!r} ({path})")
    doc = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(doc)
    return Draft202012Validator(doc, registry=_registry(sdir), format_checker=FormatChecker())


def errors(name: str, instance: object, schemas_dir: str | None = None) -> list[str]:
    """Actionable, sorted error messages: '<json path>: <message>'."""
    v = validator(name, schemas_dir)
    out = []
    for e in sorted(v.iter_errors(instance), key=lambda e: list(map(str, e.absolute_path))):
        loc = "/" + "/".join(str(p) for p in e.absolute_path)
        out.append(f"{loc}: {e.message}")
    return out


def check(name: str, instance: object, what: str = "document") -> None:
    errs = errors(name, instance)
    if errs:
        raise SchemaError(f"{what} fails {schema_name(name)}:\n  " + "\n  ".join(errs[:50]))


class SchemaError(ValueError):
    pass
