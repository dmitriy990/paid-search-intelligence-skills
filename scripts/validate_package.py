#!/usr/bin/env python3
"""Validate the paid-search-intelligence skill package.

Usage: python3 scripts/validate_package.py [repo_root]

Checks required files, SKILL.md frontmatter, word budgets per role load, relative links,
role commands, behavioural eval cases, manifests, and credential-like strings.
Exits 0 when every check passes, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
SKILL_NAME = "paid-search-intelligence"

SHARED = "shared-operating-system.md"
ROLE_FILES = {
    "analyst": "analyst.md",
    "optimizer": "optimizer.md",
    "pm": "product-manager.md",
    "crisis": "operating-rhythm-and-crisis.md",
}
SQL = "sql-patterns.md"
REFERENCES = [SHARED, *ROLE_FILES.values(), SQL]
COMMANDS = [f"paid-search-{role}.md" for role in ROLE_FILES]

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "LICENSE",
    *(f"references/{name}" for name in REFERENCES),
    *(f"commands/{name}" for name in COMMANDS),
    "evals/cases.json",
    "evals/JUDGE.md",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".github/workflows/validate.yml",
    "scripts/validate_package.py",
]

SKILL_WORD_BUDGET = 1500
ROLE_LOAD_WORD_BUDGET = 5000  # SKILL.md + shared rules + one role file
SQL_WORD_BUDGET = 1000        # loaded on demand when queries are written
MIN_EVAL_CASES = 10
EVAL_ROLES = {*ROLE_FILES, "any"}
REQUIRED_CATEGORIES = {
    "data_truth",
    "privacy",
    "role_boundary",
    "read_only_sql",
    "instruction_integrity",
    "conversion_lag",
    "routing",
}
CASE_FIELDS = {"id", "role", "category", "prompt", "input", "requirements", "prohibitions"}
RESERVED_MARKETPLACE_NAMES = {"agent-skills", "claude-plugins-official", "anthropic-marketplace"}
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"ya29\.[0-9A-Za-z_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r'"private_key"\s*:'),
    re.compile(r"\b\d{3}-\d{3}-\d{4}\b"),  # Google Ads customer ID, 123-456-7890
]

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def read(rel: str) -> str | None:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except OSError:
        return None


def words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def load_json(rel: str):
    text = read(rel)
    if text is None:
        return None, f"cannot read {rel}"
    try:
        return json.loads(text), ""
    except json.JSONDecodeError as exc:
        return None, f"{rel}: {exc}"


def frontmatter(text: str) -> dict | None:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            value = value.strip()
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = value.strip('"')
            fields[key.strip()] = value
    version = re.search(r"^\s+version:\s*[\"']?(\d+\.\d+\.\d+)[\"']?\s*$", m.group(1), re.M)
    fields["_version"] = version.group(1) if version else None
    return fields


def relative_links(text: str) -> list[str]:
    links = re.findall(r"\]\(([^)\s]+)\)", text)
    return [l.split("#")[0] for l in links if not re.match(r"^([a-z]+:|#)", l) and l.split("#")[0]]


# 1. Required files -----------------------------------------------------------
missing = [p for p in REQUIRED_FILES if not (ROOT / p).is_file()]
check(f"{len(REQUIRED_FILES)} required files exist", not missing, "missing: " + ", ".join(missing))

# 2. Frontmatter ----------------------------------------------------------------
skill = read("SKILL.md")
fm = frontmatter(skill) if skill else None
check("SKILL.md has frontmatter", fm is not None)
skill_version = None
if fm is not None:
    description = fm.get("description", "")
    skill_version = fm.get("_version")
    check("name is the skill name", fm.get("name") == SKILL_NAME, repr(fm.get("name")))
    check("description is non-empty and at most 1,024 characters", 0 < len(description) <= 1024,
          f"{len(description)} characters")
    check("license is declared", bool(fm.get("license")))
    check("metadata.version is semantic", skill_version is not None)

# 3. Word budgets --------------------------------------------------------------
refs = {name: read(f"references/{name}") for name in REFERENCES}
if skill is not None and all(v is not None for v in refs.values()):
    skill_words = words(skill)
    check(f"SKILL.md is {skill_words} words (budget {SKILL_WORD_BUDGET})", skill_words <= SKILL_WORD_BUDGET)
    for role, name in ROLE_FILES.items():
        load = skill_words + words(refs[SHARED]) + words(refs[name])
        check(f"{role} load is {load} words (budget {ROLE_LOAD_WORD_BUDGET})", load <= ROLE_LOAD_WORD_BUDGET)
    sql_words = words(refs[SQL])
    check(f"{SQL} is {sql_words} words (budget {SQL_WORD_BUDGET})", sql_words <= SQL_WORD_BUDGET)
    peak = skill_words + words(refs[SHARED]) + words(refs[ROLE_FILES["analyst"]]) + sql_words
    print(f"INFO  analyst load plus {SQL}: {peak} words (loaded when queries are written)")
else:
    check("word budgets can be measured", False, "SKILL.md or a reference file is missing")

# 4. Links ---------------------------------------------------------------------
if skill is not None:
    linked = {Path(l).name for l in relative_links(skill) if l.startswith("references/")}
    unlinked = [n for n in REFERENCES if n not in linked]
    check("every reference is linked from SKILL.md", not unlinked, ", ".join(unlinked))
link_sources = ["SKILL.md", "README.md", *(f"commands/{c}" for c in COMMANDS)]
broken, stale = [], []
for rel in link_sources:
    text = read(rel)
    if text is None:
        continue
    base = (ROOT / rel).parent
    for link in relative_links(text):
        if not (base / link).exists() and not (ROOT / link).exists():
            broken.append(f"{rel} -> {link}")
    if re.search(r"(?<![\w./~-])skills/paid-search-intelligence/(?:SKILL\.md|references)", text):
        stale.append(rel)
check("every relative link resolves", not broken, "; ".join(broken))
check("no reference to the old skills/ folder layout", not stale, ", ".join(stale))

# 5. Role commands ----------------------------------------------------------------
bad_commands = []
for name in COMMANDS:
    text = read(f"commands/{name}")
    cfm = frontmatter(text) if text else None
    if not (text and cfm and cfm.get("description") and f"`{SKILL_NAME}`" in text and "$ARGUMENTS" in text):
        bad_commands.append(name)
check("each command has a description, names the skill and takes $ARGUMENTS", not bad_commands,
      ", ".join(bad_commands))

# 6. Behavioural evals --------------------------------------------------------------
payload, err = load_json("evals/cases.json")
cases = payload.get("cases", []) if isinstance(payload, dict) else []
check("evals/cases.json parses", payload is not None, err)
if payload is not None:
    ids = [c.get("id") for c in cases if isinstance(c, dict)]
    malformed = [
        str(c.get("id", i)) if isinstance(c, dict) else f"case {i}"
        for i, c in enumerate(cases)
        if not isinstance(c, dict)
        or not CASE_FIELDS <= set(c)
        or not c.get("requirements")
        or not c.get("prohibitions")
        or c.get("role") not in EVAL_ROLES
    ]
    categories = {c.get("category") for c in cases if isinstance(c, dict)}
    check(f"at least {MIN_EVAL_CASES} eval cases ({len(cases)} found)", len(cases) >= MIN_EVAL_CASES)
    check("eval case ids are unique", len(ids) == len(set(ids)))
    check("eval cases have every required field and a valid role", not malformed, ", ".join(malformed))
    check("eval categories cover the required set", REQUIRED_CATEGORIES <= categories,
          "missing: " + ", ".join(sorted(REQUIRED_CATEGORIES - categories)))

# 7. Manifests --------------------------------------------------------------------------
plugin, err1 = load_json(".claude-plugin/plugin.json")
market, err2 = load_json(".claude-plugin/marketplace.json")
check("plugin.json and marketplace.json parse", plugin is not None and market is not None, err1 or err2)
if plugin is not None:
    check("plugin name is the skill name", plugin.get("name") == SKILL_NAME, repr(plugin.get("name")))
    check("plugin version equals SKILL.md metadata.version", plugin.get("version") == skill_version,
          f"plugin.json {plugin.get('version')!r} vs SKILL.md {skill_version!r}")
    check("plugin declares description, author and license",
          bool(plugin.get("description") and (plugin.get("author") or {}).get("name") and plugin.get("license")))
if market is not None:
    check("marketplace name is valid and not reserved",
          bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", market.get("name", "")))
          and market.get("name") not in RESERVED_MARKETPLACE_NAMES, repr(market.get("name")))
    check("marketplace owner has a name", bool((market.get("owner") or {}).get("name")))
    entry = next((e for e in market.get("plugins", []) if e.get("name") == SKILL_NAME), None)
    check("marketplace lists the plugin", entry is not None)
    if entry is not None:
        src = entry.get("source")
        check("entry source is the repo root and omits version",
              src in (".", "./") and "version" not in entry, f"source={src!r}")

# 8. Credential-like strings ------------------------------------------------------------------
scan = ["SKILL.md", "README.md", "evals/cases.json", "evals/JUDGE.md",
        *(f"references/{n}" for n in REFERENCES), *(f"commands/{c}" for c in COMMANDS),
        ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"]
hits = [f"{rel} ~ {rx.pattern[:24]}" for rel in scan if (text := read(rel))
        for rx in SECRET_PATTERNS if rx.search(text)]
check("no credential or customer-ID patterns in shipped files", not hits, "; ".join(hits))

print()
if failures:
    print(f"{len(failures)} validation failure(s)")
    sys.exit(1)
print("Package validation passed")
