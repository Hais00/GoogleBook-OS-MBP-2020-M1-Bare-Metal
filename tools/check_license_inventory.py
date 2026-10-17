#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 GoogleBook OS port contributors
"""Check publication inventory consistency; this is not legal-rights clearance."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def resolve(name):
    path = ROOT / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(ROOT):
        raise ValueError(f"Path outside repository: {name}")
    return path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def leading_spdx(path):
    lines = path.read_text().splitlines()
    limit = 3 if path.suffix in {".py", ".sh"} else 25
    match = re.search(
        r"(?m)^\s*(?://|#|/\*|\*)\s*SPDX-License-Identifier:\s*([^\r\n*]+)",
        "\n".join(lines[:limit]),
    )
    return match.group(1).strip() if match else None


def normalized(expression):
    aliases = {"GPL-2.0": "GPL-2.0-only", "GPL-2.0+": "GPL-2.0-or-later"}
    return aliases.get(expression, expression)


def check():
    audit = json.loads(resolve("manifests/license-audit.json").read_text())
    source_entries = {entry["file"]: entry for entry in audit["files"]}
    patch_entries = {entry["file"]: entry for entry in audit["patches"]}
    if len(source_entries) != len(audit["files"]) or len(patch_entries) != len(audit["patches"]):
        raise ValueError("Duplicate inventory entry")
    documents = {entry["file"]: entry for entry in audit["license_documents"]}
    required = set()
    for directory in ("scripts", "sources", "config", "tools", "patches"):
        for path in resolve(directory).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".md"}:
                continue
            relative = str(path.relative_to(ROOT))
            if relative in documents:
                continue
            required.add(relative)
    actual = set(source_entries) | set(patch_entries)
    if required != actual:
        raise ValueError(f"Inventory coverage mismatch: missing={sorted(required-actual)}, stale={sorted(actual-required)}")
    for name, entry in {**source_entries, **patch_entries}.items():
        path = resolve(name)
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"Stale inventory hash: {name}")
        expressions = [entry["license_expression"]] if name in source_entries else [x["license_expression"] for x in entry["file_license_scopes"]]
        for expression in expressions:
            for token in expression.replace("(", " ").replace(")", " ").split():
                if token not in {"OR", "AND", "WITH"} and not resolve(f"LICENSES/{token}.txt").is_file():
                    raise ValueError(f"Missing license/exception text: {name}: {token}")
        if name in patch_entries:
            members = re.findall(r"^\+\+\+ b/(.+)$", path.read_text(), re.M)
            if not members or members != entry["upstream_files"] or members != [item["path"] for item in entry["file_license_scopes"]]:
                raise ValueError(f"Patch member/license scope mismatch: {name}")
        if name in source_entries:
            declared = leading_spdx(path)
            if declared and normalized(declared) != entry["license_expression"]:
                raise ValueError(f"Header/inventory license mismatch: {name}")
            if entry.get("modification_notice_date") and "Modified for GoogleBook OS on 2026-10-17." not in path.read_text():
                raise ValueError(f"Missing recorded modification notice: {name}")
    for name, entry in documents.items():
        if sha256(resolve(name)) != entry["sha256"]:
            raise ValueError(f"Changed verbatim license/notice: {name}")
    for record in json.loads(resolve("manifests/source-export.json").read_text())["records"]:
        if sha256(resolve(record["file"])) != record["published_sha256"]:
            raise ValueError(f"Stale source-export hash: {record['file']}")
    for name in ("LICENSE", "LICENSING.md", "THIRD_PARTY_NOTICES.md", "NOTICE"):
        if not resolve(name).is_file():
            raise ValueError(f"Missing license index or supporting notice: {name}")
    print(f"License inventory consistency PASS: {len(source_entries)} source/config files, {len(patch_entries)} patches, {len(documents)} license/notice documents")
    print("Scope: mechanical publication checks only; no binary or legal-rights clearance.")


if __name__ == "__main__":
    try:
        check()
    except (ValueError, KeyError, OSError) as error:
        print(f"License inventory consistency FAIL: {error}", file=sys.stderr)
        sys.exit(1)
