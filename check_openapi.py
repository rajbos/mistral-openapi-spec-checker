#!/usr/bin/env python3
import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml


METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
DOCS = "https://docs.mistral.ai/api"
API = "https://api.mistral.ai"


def load_spec(path):
    with open(path, encoding="utf-8") as file:
        spec = yaml.safe_load(file)
    if not isinstance(spec, dict) or not str(spec.get("openapi", "")).startswith("3."):
        raise ValueError(f"{path} is not an OpenAPI 3 specification")
    if not isinstance(spec.get("paths"), dict) or not spec["paths"]:
        raise ValueError(f"{path} has no API paths")
    return spec


def operations(spec):
    result = {}
    for path, item in spec["paths"].items():
        if not isinstance(path, str) or not path.startswith("/") or not isinstance(item, dict):
            raise ValueError(f"Invalid path item: {path!r}")
        if any(not isinstance(key, str) for key in item):
            raise ValueError(f"Invalid path item key: {path}")
        common = {key: value for key, value in item.items() if key.lower() not in METHODS}
        for method, operation in item.items():
            if method.lower() in METHODS:
                if not isinstance(operation, dict):
                    raise ValueError(f"Invalid operation: {method} {path}")
                security = operation.get("security", spec.get("security"))
                schemes = spec.get("components", {}).get("securitySchemes", {})
                security_names = {
                    name for requirement in security or [] if isinstance(requirement, dict)
                    for name in requirement
                }
                result[(path, method.upper())] = {
                    "operation": operation,
                    "path": common,
                    "security": security,
                    "securitySchemes": {name: schemes.get(name) for name in security_names},
                    "servers": spec.get("servers"),
                }
    if not result:
        raise ValueError("Specification contains no operations")
    for entry in result.values():
        referenced_components(spec, entry)
    return result


def referenced_components(spec, value):
    found = {}

    def resolve(ref, scope):
        for root in (scope, spec) if scope is not spec else (spec,):
            target = root
            try:
                for part in ref[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
                return target, root
            except (KeyError, TypeError):
                pass
        raise ValueError(f"Unresolved reference: {ref}") from None

    def visit(node, scope):
        if isinstance(node, dict):
            if "$defs" in node:
                scope = node
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/") and ref not in found:
                target, target_scope = resolve(ref, scope)
                found[ref] = target
                visit(target, target_scope)
            for child in node.values():
                visit(child, scope)
        elif isinstance(node, list):
            for child in node:
                visit(child, scope)

    visit(value, spec)
    return found


MISSING = object()


def changed_fields(old, new, prefix=""):
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(old.keys() | new.keys(), key=str):
            name = f"{prefix}.{key}" if prefix else str(key)
            if key not in old or key not in new:
                yield name, old.get(key, MISSING), new.get(key, MISSING)
            else:
                yield from changed_fields(old[key], new[key], name)
    elif old != new:
        yield prefix, old, new


def value_summary(value):
    if value is MISSING:
        return "(absent)"
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > 160:
        text = text[:157] + "..."
    return html.escape(text).replace("`", "&#96;")


def documentation(operation):
    external = operation.get("externalDocs")
    if isinstance(external, dict) and isinstance(external.get("url"), str):
        url = external["url"]
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.netloc == "docs.mistral.ai":
            return url.replace(")", "%29").replace("(", "%28")
    tags = operation.get("tags")
    if isinstance(tags, list) and tags and isinstance(tags[0], str):
        tag = tags[0]
        if re.fullmatch(r"[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*", tag):
            return f"{DOCS}/endpoint/{tag.replace('.', '/')}"
    return DOCS


def describe(operation):
    description = operation.get("description") or operation.get("summary") or "No description provided."
    return html.escape(" ".join(str(description).split()))


def render(old_spec, new_spec):
    new = operations(new_spec)
    if old_spec is None:
        return ("# Initial OpenAPI baseline\n\n"
                "The current specification has been saved as the baseline. "
                "Future releases will describe endpoint changes.\n")

    old = operations(old_spec)
    sections = {"Added": [], "Changed": [], "Removed": []}
    for key in sorted(old.keys() | new.keys()):
        before, after = old.get(key), new.get(key)
        if before is None:
            category, entry = "Added", after
        elif after is None:
            category, entry = "Removed", before
        else:
            before_refs = referenced_components(old_spec, before)
            after_refs = referenced_components(new_spec, after)
            fields = list(changed_fields(before, after))
            fields += list(changed_fields(before_refs, after_refs, "references"))
            if not fields:
                continue
            category, entry = "Changed", after
        path, method = key
        operation = entry["operation"]
        lines = [f"### `{method} {API}{path}`",
                 f"{describe(operation)}",
                 f"[Documentation]({documentation(operation)})"]
        if category == "Changed":
            shown = [
                f"- `{html.escape(field).replace('`', '&#96;')}`: "
                f"`{value_summary(before_value)}` → `{value_summary(after_value)}`"
                for field, before_value, after_value in fields[:20]
            ]
            if len(fields) > 20:
                shown.append(f"- and {len(fields) - 20} more changed fields")
            lines.append("Changed fields:\n" + "\n".join(shown))
        sections[category].append("\n\n".join(lines))
    if not any(sections.values()):
        return ""
    return "# Mistral API changes\n\n" + "\n\n".join(
        f"## {name}\n\n" + "\n\n".join(entries)
        for name, entries in sections.items() if entries
    ) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current = load_spec(args.current)
    previous = load_spec(args.previous) if args.previous else None
    args.output.write_text(render(previous, current), encoding="utf-8")


if __name__ == "__main__":
    main()
