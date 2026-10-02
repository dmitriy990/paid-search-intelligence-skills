#!/usr/bin/env python3
"""Validate the paid-search-intelligence skill package.

Usage:
  python3 scripts/validate_package.py [repo_root]     validate the package
  python3 scripts/validate_package.py --self-test     prove the validator fails on broken copies

Checks: required files and their content; SKILL.md and command frontmatter (strict subset, plus
a real YAML parse when PyYAML is installed); word budgets for every load a session can make;
relative links in every Markdown file; role commands; eval cases; manifests against SKILL.md
and README; credential-like strings in every file of the package.
Exits 0 when every check passes, 1 otherwise. Standard library only (PyYAML optional).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # optional: CI installs it, so the real parse always runs there
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

SKILL_NAME = "paid-search-intelligence"

# reference file -> (first heading, section markers that must be present)
REFERENCES = {
    "shared-operating-system.md": ("# PART A", [f"## A{i}." for i in range(1, 10)]),
    "analyst.md": ("# PART B", [f"## B{i}." for i in range(1, 7)]),
    "optimizer.md": ("# PART C", [f"## C{i}." for i in range(1, 7)]),
    "product-manager.md": ("# PART D", [f"## D{i}." for i in range(1, 11)]),
    "operating-rhythm-and-crisis.md": ("# PART E", ["## E1.", "## E2."]),
    "sql-patterns.md": ("# APPENDIX", ["**1. ", "**1b. ", "**2. ", "**3. ", "**3b. ", "**4. ", "**5. ", "**5b. "]),
}
SHARED, SQL = "shared-operating-system.md", "sql-patterns.md"
ROLE_FILES = {
    "analyst": "analyst.md",
    "optimizer": "optimizer.md",
    "pm": "product-manager.md",
    "crisis": "operating-rhythm-and-crisis.md",
}
# command file -> phrase that ties it to its own role
COMMANDS = {
    "paid-search-analyst.md": "as the Analyst",
    "paid-search-optimizer.md": "as the Optimizer",
    "paid-search-pm.md": "as the Product Manager",
    "paid-search-crisis.md": "crisis protocol",
}
SKILL_SECTIONS = [
    "## How to use these instructions",
    "## Choose a role",
    "## Load order",
    "## No BigQuery tool, or pasted data",
    "## Hard rules",
]
REQUIRED_FILES = [
    "SKILL.md", "README.md", "LICENSE",
    *(f"references/{n}" for n in REFERENCES),
    *(f"commands/{n}" for n in COMMANDS),
    "evals/cases.json", "evals/JUDGE.md",
    ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
    ".github/workflows/validate.yml", "scripts/validate_package.py",
]
MIN_BYTES = {"README.md": 1500, "LICENSE": 500, "evals/JUDGE.md": 1500, ".github/workflows/validate.yml": 200}
MIN_REFERENCE_BYTES = 3000

# Budgets in words (whitespace-separated, as `wc -w`) and bytes. Every load a session can make.
WORDS, BYTES = 0, 1
BUDGETS = {
    "SKILL.md": (1500, 11000),
    "role load (SKILL.md + shared rules + one role file)": (8200, 53000),
    "role load plus sql-patterns.md": (11400, 78000),
    "all roles (a chain or a crisis: SKILL.md + shared rules + four role files)": (13400, 87000),
}

EVAL_ROLES = {*ROLE_FILES, "any"}
REQUIRED_CATEGORIES = {
    "data_truth", "privacy", "role_boundary", "read_only_sql",
    "instruction_integrity", "conversion_lag", "routing",
}
ALLOWED_CATEGORIES = REQUIRED_CATEGORIES | {"crisis", "platform_facts", "answer_format", "no_tool"}
MIN_EVAL_CASES = 10
MIN_CASES_PER_ROLE = {"analyst": 2, "optimizer": 2, "pm": 2, "crisis": 2}
RULE_REF = re.compile(r"^(A[1-9]|B[1-6]|C[1-6]|D(10|[1-9])|E[12]|SKILL|SQL)$")

RESERVED_MARKETPLACE_NAMES = {
    "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official", "anthropic-marketplace",
    "anthropic-plugins", "agent-skills", "anthropic-agent-skills", "life-sciences", "knowledge-work-plugins",
    "claude-for-legal", "claude-for-financial-services", "financial-services-plugins", "first-party-plugins",
    "claude-tag-plugins", "claude-community", "claude-plugins-community", "healthcare",
    "anthropic-plugin-directory", "claude-plugin-directory", "inline", "builtin", "skills-dir", "synced",
    "claude-plugin-test", "npm", "pip", "uv", "cargo", "github", "gh",
}
SECRET_PATTERNS = [
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("OAuth access token", re.compile(r"ya29\.[0-9A-Za-z_-]{20,}")),
    ("OAuth refresh token", re.compile(r"\b1//0[0-9A-Za-z_-]{20,}")),
    ("OAuth client secret", re.compile(r"GOCSPX-[0-9A-Za-z_-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("service-account key field", re.compile(r'"private_key(_id)?"\s*:')),
    ("service-account email", re.compile(r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com")),
    ("Google Ads customer ID", re.compile(r"\b\d{3}-\d{3}-\d{4}\b")),
    ("customer ID in a table name", re.compile(r"\b(?:p_)?ads_[A-Za-z]+_\d{6,12}\b")),
    ("click identifier", re.compile(r"\b(?:gclid|gbraid|wbraid)=[0-9A-Za-z_-]{16,}")),
]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
PLAIN_SCALAR_BAD_START = tuple("[{>|*&!%@`\"'#-?,")


def words(text: str) -> int:
    return len(text.split())


def repo_files(root: Path) -> list[str]:
    """Files of the package: tracked plus untracked-not-ignored when in git, otherwise a walk."""
    if (root / ".git").exists():
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                capture_output=True, check=True,
            ).stdout.decode("utf-8", "replace")
            return sorted({f for f in out.split("\0") if f and (root / f).is_file()})
        except (OSError, subprocess.CalledProcessError):
            pass
    found = []
    for path in root.rglob("*"):
        if path.is_file() and not (set(path.relative_to(root).parts[:-1]) & SKIP_DIRS):
            found.append(path.relative_to(root).as_posix())
    return sorted(found)


def split_frontmatter(text: str):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1), text[m.end():]) if m else (None, text)


def parse_scalar(raw: str):
    """A value we accept: a JSON double-quoted string, or a plain scalar that every YAML loader reads as a string."""
    raw = raw.strip()
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None, "not a valid double-quoted string"
        return (value, "") if isinstance(value, str) else (None, "not a string")
    if not raw:
        return None, "empty"
    if raw.startswith(PLAIN_SCALAR_BAD_START) or ": " in raw or " #" in raw or raw.endswith(":") or "\t" in raw:
        return None, "unquoted value that YAML could misread; put it in double quotes"
    if raw.lower() in {"true", "false", "null", "yes", "no", "on", "off", "~"} or re.fullmatch(r"[-+]?[\d.]+", raw):
        return None, "would not parse as a string; put it in double quotes"
    return raw, ""


def parse_frontmatter(block: str, allowed: set[str], nested: dict[str, set[str]]):
    """Strict subset: `key: value` lines, plus `key:` followed by two-space-indented `sub: value` lines."""
    fields, errors, current = {}, [], None
    for n, line in enumerate(block.split("\n"), 1):
        if not line.strip():
            continue
        if "\t" in line:
            errors.append(f"line {n}: tab character")
            continue
        m = re.match(r"^( {0,2})([A-Za-z][A-Za-z0-9_-]*):(.*)$", line)
        if not m or len(m.group(1)) == 1:
            errors.append(f"line {n}: not a `key: value` line")
            continue
        indent, key, rest = len(m.group(1)), m.group(2), m.group(3)
        if indent == 0:
            current = None
            if key not in allowed:
                errors.append(f"line {n}: unknown key {key!r}")
                continue
            if key in fields:
                errors.append(f"line {n}: duplicate key {key!r}")
                continue
            if key in nested:
                if rest.strip():
                    errors.append(f"line {n}: {key!r} must be a block")
                fields[key], current = {}, key
            else:
                value, err = parse_scalar(rest)
                if err:
                    errors.append(f"line {n}: {key}: {err}")
                fields[key] = value
        else:
            if current is None or key not in nested.get(current, set()):
                errors.append(f"line {n}: unexpected nested key {key!r}")
                continue
            value, err = parse_scalar(rest)
            if err:
                errors.append(f"line {n}: {current}.{key}: {err}")
            fields[current][key] = value
    return fields, errors


def yaml_agrees(block: str, fields: dict):
    """When PyYAML is present, the real parse must succeed and give the same values."""
    if yaml is None:
        return True, "PyYAML not installed; strict subset check only"
    try:
        loaded = yaml.safe_load(block)
    except Exception as exc:  # noqa: BLE001
        return False, f"YAML error: {str(exc).splitlines()[0]}"
    return (loaded == fields, "" if loaded == fields else f"YAML parse differs from the strict parse: {loaded!r}")


def relative_links(text: str) -> list[str]:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return [l for l in re.findall(r"\]\(([^)\s]+)\)", text) if not re.match(r"^([A-Za-z][A-Za-z0-9+.-]*:|#)", l)]


def load_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8")), ""
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"{rel}: {exc}"


def validate(root: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> bool:
        results.append((label, bool(ok), detail))
        return bool(ok)

    def read(rel: str):
        try:
            return (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    files = repo_files(root)

    # 1. Required files and their content -------------------------------------------------
    missing = [p for p in REQUIRED_FILES if not (root / p).is_file()]
    check(f"{len(REQUIRED_FILES)} required files exist", not missing, "missing: " + ", ".join(missing))
    small = [f"{p} ({len((root / p).read_bytes())} bytes)" for p, n in MIN_BYTES.items()
             if (root / p).is_file() and len((root / p).read_bytes()) < n]
    check("README, LICENSE, JUDGE.md and the workflow are not empty shells", not small, ", ".join(small))

    refs = {name: read(f"references/{name}") for name in REFERENCES}
    bad_refs = []
    for name, (heading, sections) in REFERENCES.items():
        text = refs[name]
        if text is None:
            continue
        if len(text.encode()) < MIN_REFERENCE_BYTES:
            bad_refs.append(f"{name}: under {MIN_REFERENCE_BYTES} bytes")
        if not text.startswith(heading):
            bad_refs.append(f"{name}: does not start with {heading!r}")
        absent = [s for s in sections if s not in text]
        if absent:
            bad_refs.append(f"{name}: missing {', '.join(absent)}")
    check("every reference has its heading, its sections and real content", not bad_refs, "; ".join(bad_refs))
    on_disk = sorted(Path(f).name for f in files if f.startswith("references/"))
    check("references/ holds exactly the known files (a new file needs a budget)",
          on_disk == sorted(REFERENCES), f"found {on_disk}")

    # 2. SKILL.md frontmatter and structure -------------------------------------------------
    skill = read("SKILL.md")
    skill_version, header_version, license_name = None, None, None
    if check("SKILL.md is readable", skill is not None):
        block, body = split_frontmatter(skill)
        if check("SKILL.md has frontmatter", block is not None):
            fm, errors = parse_frontmatter(block, {"name", "description", "license", "metadata"}, {"metadata": {"version"}})
            check("SKILL.md frontmatter uses only the strict subset", not errors, "; ".join(errors))
            ok, detail = yaml_agrees(block, fm)
            check("SKILL.md frontmatter parses as YAML to the same values", ok, detail)
            description = fm.get("description") or ""
            skill_version = (fm.get("metadata") or {}).get("version") if isinstance(fm.get("metadata"), dict) else None
            license_name = fm.get("license")
            check("name is the skill name", fm.get("name") == SKILL_NAME, repr(fm.get("name")))
            check("description is a string of 1 to 1,024 characters",
                  isinstance(description, str) and 0 < len(description) <= 1024, f"{len(description)} characters")
            check("license is declared", bool(license_name))
            check("metadata.version is semantic", isinstance(skill_version, str)
                  and bool(re.fullmatch(r"\d+\.\d+\.\d+", skill_version)), repr(skill_version))
        absent = [s for s in SKILL_SECTIONS if s not in body]
        check("SKILL.md has its sections", not absent, "missing: " + ", ".join(absent))
        m = re.search(r"^# Paid Search Intelligence Team — Instructions — v(\d+\.\d+) \(\d{4}-\d{2}-\d{2}\)$", body, re.M)
        header_version = m.group(1) if m else None
        check("SKILL.md carries the instruction version header", header_version is not None)
        check("header version matches metadata.version (major.minor)",
              bool(header_version and skill_version and skill_version.startswith(header_version + ".")),
              f"header v{header_version} vs metadata {skill_version}")

    # 3. Budgets ------------------------------------------------------------------------------
    if skill is not None and all(v is not None for v in refs.values()):
        def size(*texts):
            return sum(words(t) for t in texts), sum(len(t.encode()) for t in texts)
        roles = [refs[n] for n in ROLE_FILES.values()]
        loads = {"SKILL.md": size(skill)}
        heaviest = max(roles, key=words)
        loads["role load (SKILL.md + shared rules + one role file)"] = size(skill, refs[SHARED], heaviest)
        loads["role load plus sql-patterns.md"] = size(skill, refs[SHARED], heaviest, refs[SQL])
        loads["all roles (a chain or a crisis: SKILL.md + shared rules + four role files)"] = size(skill, refs[SHARED], *roles)
        for name, (w, b) in loads.items():
            limit = BUDGETS[name]
            check(f"{name}: {w:,} words, {b:,} bytes (budget {limit[WORDS]:,} words, {limit[BYTES]:,} bytes)",
                  w <= limit[WORDS] and b <= limit[BYTES])
    else:
        check("budgets can be measured", False, "SKILL.md or a reference file is missing")

    # 4. Links ------------------------------------------------------------------------------------
    if skill is not None:
        linked = {Path(l.split("#")[0]).name for l in relative_links(skill) if l.startswith("references/")}
        unlinked = [n for n in REFERENCES if n not in linked]
        check("every reference is linked from SKILL.md", not unlinked, ", ".join(unlinked))
    broken, stale = [], []
    for rel in [f for f in files if f.endswith(".md")]:
        text = read(rel)
        if text is None:
            continue
        base = (root / rel).parent
        for link in relative_links(text):
            target = link.split("#")[0]
            if not target:
                continue
            resolved = (base / target).resolve()
            if target.startswith("/") or root.resolve() not in [resolved, *resolved.parents] or not resolved.exists():
                broken.append(f"{rel} -> {link}")
        if re.search(r"(?<![\w.~-])(?:\./)?skills/paid-search-intelligence/(?:SKILL\.md|references)", re.sub(r"~/\.claude/skills/\S*", "", text)):
            stale.append(rel)
    check("every relative link resolves from the file that contains it", not broken, "; ".join(broken))
    check("no reference to the old skills/ folder layout", not stale, ", ".join(stale))

    # 5. Role commands ----------------------------------------------------------------------------
    problems = []
    for name, phrase in COMMANDS.items():
        text = read(f"commands/{name}")
        if text is None:
            continue
        block, body = split_frontmatter(text)
        if block is None:
            problems.append(f"{name}: no frontmatter")
            continue
        fm, errors = parse_frontmatter(block, {"description", "argument-hint"}, {})
        ok, detail = yaml_agrees(block, fm)
        visible = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        if errors or not ok:
            problems.append(f"{name}: {'; '.join(errors) or detail}")
        if not fm.get("description") or not isinstance(fm.get("argument-hint"), str):
            problems.append(f"{name}: needs a description and a quoted argument-hint")
        if f"`{SKILL_NAME}`" not in visible or "$ARGUMENTS" not in visible:
            problems.append(f"{name}: must name the skill and take $ARGUMENTS")
        if phrase not in visible:
            problems.append(f"{name}: does not invoke its own role ({phrase!r})")
    extra = sorted(Path(f).name for f in files if f.startswith("commands/") and Path(f).name not in COMMANDS)
    if extra:
        problems.append("unknown command files: " + ", ".join(extra))
    check("each command is valid, invokes its own role and takes $ARGUMENTS", not problems, "; ".join(problems))

    # 6. Behavioural evals ---------------------------------------------------------------------------
    payload, err = load_json(root, "evals/cases.json")
    if check("evals/cases.json parses", payload is not None, err):
        cases = payload.get("cases") if isinstance(payload, dict) else None
        cases = cases if isinstance(cases, list) else []

        def text_list(v):
            return isinstance(v, list) and len(v) > 0 and all(isinstance(x, str) and x.strip() for x in v)

        malformed = []
        for i, c in enumerate(cases):
            label = c.get("id") if isinstance(c, dict) and isinstance(c.get("id"), str) else f"case {i}"
            if not isinstance(c, dict):
                malformed.append(f"{label}: not an object")
                continue
            if not (isinstance(c.get("id"), str) and c["id"].strip()):
                malformed.append(f"{label}: id")
            if c.get("role") not in EVAL_ROLES:
                malformed.append(f"{label}: role")
            if c.get("category") not in ALLOWED_CATEGORIES:
                malformed.append(f"{label}: category")
            if not (isinstance(c.get("prompt"), str) and c["prompt"].strip()):
                malformed.append(f"{label}: prompt")
            if not isinstance(c.get("input"), str):
                malformed.append(f"{label}: input")
            if not text_list(c.get("requirements")):
                malformed.append(f"{label}: requirements")
            if not text_list(c.get("prohibitions")):
                malformed.append(f"{label}: prohibitions")
            if not (text_list(c.get("rule_refs")) and all(RULE_REF.match(r) for r in c["rule_refs"])):
                malformed.append(f"{label}: rule_refs")
        good = [c for c in cases if isinstance(c, dict)]
        ids = [c.get("id") for c in good]
        prompts = [(c.get("prompt"), c.get("input")) for c in good]
        check(f"at least {MIN_EVAL_CASES} eval cases ({len(cases)} found)", len(cases) >= MIN_EVAL_CASES)
        check("eval cases are well formed (types, role, category, rule_refs)", not malformed, "; ".join(malformed[:12]))
        check("eval case ids are unique", len(ids) == len(set(map(str, ids))))
        check("no two eval cases share prompt and input", len(prompts) == len(set(map(str, prompts))))
        categories = {c.get("category") for c in good}
        check("eval categories cover the required set", REQUIRED_CATEGORIES <= categories,
              "missing: " + ", ".join(sorted(REQUIRED_CATEGORIES - categories)))
        thin = [f"{r} ({sum(1 for c in good if c.get('role') == r)})" for r, n in MIN_CASES_PER_ROLE.items()
                if sum(1 for c in good if c.get("role") == r) < n]
        check("every role has at least two eval cases", not thin, ", ".join(thin))
    judge = read("evals/JUDGE.md") or ""
    check("JUDGE.md applies each case's requirements and prohibitions",
          "requirement" in judge.lower() and "prohibition" in judge.lower())

    # 7. Manifests, license and README -------------------------------------------------------------------
    plugin, err1 = load_json(root, ".claude-plugin/plugin.json")
    market, err2 = load_json(root, ".claude-plugin/marketplace.json")
    check("plugin.json and marketplace.json parse", plugin is not None and market is not None, err1 or err2)
    plugin = plugin if isinstance(plugin, dict) else {}
    market = market if isinstance(market, dict) else {}
    readme = read("README.md") or ""
    license_text = read("LICENSE") or ""
    author = plugin.get("author") if isinstance(plugin.get("author"), dict) else {}
    owner = market.get("owner") if isinstance(market.get("owner"), dict) else {}
    entries = [e for e in market.get("plugins", []) if isinstance(e, dict)] if isinstance(market.get("plugins"), list) else []

    check("plugin name is the skill name", plugin.get("name") == SKILL_NAME, repr(plugin.get("name")))
    check("plugin version equals SKILL.md metadata.version", bool(skill_version) and plugin.get("version") == skill_version,
          f"plugin.json {plugin.get('version')!r} vs SKILL.md {skill_version!r}")
    check("plugin declares description, author.name and license",
          bool(isinstance(plugin.get("description"), str) and plugin["description"].strip() and author.get("name") and plugin.get("license")))
    check("license agrees in SKILL.md, plugin.json and LICENSE",
          bool(license_name) and plugin.get("license") == license_name and f"{license_name} License" in license_text,
          f"SKILL.md {license_name!r}, plugin.json {plugin.get('license')!r}")
    declared = [(k, p) for k in ("skills", "commands", "agents", "hooks") if isinstance(plugin.get(k), (str, list))
                for p in ([plugin[k]] if isinstance(plugin[k], str) else plugin[k]) if isinstance(p, str)]
    absent = [f"{k}: {p}" for k, p in declared if not (root / p).exists()]
    check("paths declared in plugin.json exist", not absent, ", ".join(absent))
    repo = plugin.get("repository") if isinstance(plugin.get("repository"), str) else ""
    slug = re.match(r"^https://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?$", repo)
    check("plugin.json has a GitHub repository URL", slug is not None, repr(repo))

    mname = market.get("name") if isinstance(market.get("name"), str) else ""
    check("marketplace name is valid and not reserved",
          bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", mname)) and mname.lower() not in RESERVED_MARKETPLACE_NAMES
          and not mname.lower().startswith("claudeai-"), repr(mname))
    check("marketplace owner has a name", bool(owner.get("name")))
    entry = next((e for e in entries if e.get("name") == SKILL_NAME), None)
    if check("marketplace lists the plugin exactly once", sum(1 for e in entries if e.get("name") == SKILL_NAME) == 1):
        check("entry source is the repo root and omits version", entry.get("source") in (".", "./") and "version" not in entry,
              f"source={entry.get('source')!r}")
        check("entry description equals the plugin.json description", entry.get("description") == plugin.get("description"))
    dangling = [str(e.get("source")) for e in entries if isinstance(e.get("source"), str) and not (root / e["source"]).exists()]
    check("every marketplace entry points at an existing path", not dangling, ", ".join(dangling))

    wanted = [f"{SKILL_NAME}@{mname}"]
    if slug:
        wanted.append(f"npx skills add {slug.group(1)}")
    if header_version:
        wanted.append(f"v{header_version}")
    absent = [w for w in wanted if w not in readme]
    check("README install commands and version match the manifests", not absent, "README lacks: " + ", ".join(absent))

    # 8. Credential-like strings in every file -------------------------------------------------------------------
    hits = []
    for rel in files:
        text = read(rel)
        if text is None:
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(text):
                hits.append(f"{rel}: {label}")
        for m in EMAIL.finditer(text):
            if m.group(1).lower() not in ALLOWED_EMAIL_DOMAINS:
                hits.append(f"{rel}: email address at {m.group(1)}")
    check(f"no credentials, customer IDs or real email addresses in {len(files)} files", not hits, "; ".join(sorted(set(hits))[:12]))
    return results


def report(results) -> int:
    for label, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  -> {detail}" if detail and not ok else ""))
    failures = [label for label, ok, _ in results if not ok]
    print()
    if failures:
        print(f"{len(failures)} validation failure(s)")
        return 1
    print("Package validation passed" + ("" if yaml else " (PyYAML not installed: frontmatter checked by the strict subset only)"))
    return 0


# --------------------------------------------------------------------------------------- self-test
def _edit(rel, fn):
    def apply(root: Path):
        path = root / rel
        path.write_text(fn(path.read_text(encoding="utf-8")), encoding="utf-8")
    return apply


def _write(rel, text):
    def apply(root: Path):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return apply


def _json(rel, fn):
    def apply(root: Path):
        path = root / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return apply


def _first_line(key, new):
    return lambda t: re.sub(rf"^{key}:.*$", new, t, count=1, flags=re.M)


def mutations():
    key = "AIza" + "B" * 35
    table = "ads_Campaign_" + "1234567890"
    return [
        ("unquoted description with a colon", _edit("SKILL.md", _first_line("description", "description: Use for paid search. Roles: Analyst"))),
        ("description with unescaped inner quotes", _edit("SKILL.md", _first_line("description", 'description: "Use for "paid search" work"'))),
        ("description as a block scalar", _edit("SKILL.md", _first_line("description", "description: >\n  " + "long text " * 400))),
        ("tab-indented version", _edit("SKILL.md", lambda t: t.replace('  version: "', '\tversion: "', 1))),
        ("metadata key renamed", _edit("SKILL.md", lambda t: t.replace("\nmetadata:\n", "\nwrongkey:\n", 1))),
        ("unknown frontmatter key", _edit("SKILL.md", lambda t: t.replace("\nlicense:", "\nallowed-tools: Bash\nlicense:", 1))),
        ("description over 1,024 characters", _edit("SKILL.md", _first_line("description", 'description: "' + "x" * 1100 + '"'))),
        ("header version differs from metadata", _edit("SKILL.md", lambda t: re.sub(r"— v\d+\.\d+ \(", "— v9.9 (", t, count=1))),
        ("SKILL.md loses its hard rules", _edit("SKILL.md", lambda t: t.replace("## Hard rules", "## Notes", 1))),
        ("empty role file", _write("references/optimizer.md", "")),
        ("role file reduced to a stub", _write("references/analyst.md", "# PART B — ANALYST\n\nTODO\n")),
        ("role file loses a section", _edit("references/product-manager.md", lambda t: t.replace("## D7.", "## D7x", 1))),
        ("unbudgeted reference file", _write("references/extra-playbook.md", "# Extra\n\n" + "word " * 20000)),
        ("symbol padding in a reference", _edit("references/sql-patterns.md", lambda t: t + "\n" + "=>|<>|;;()[]{} " * 20000)),
        ("oversized SKILL.md", _edit("SKILL.md", lambda t: t + "\n" + "word " * 700)),
        ("API key in LICENSE", _edit("LICENSE", lambda t: t + "\n" + key + "\n")),
        ("private key in a new file", _write("evals/fixtures/key.json", '{"' + 'private_key' + '": "x"}\n')),
        ("customer ID in a table name", _edit("README.md", lambda t: t + "\nSee " + table + "\n")),
        ("real email address", _edit("README.md", lambda t: t + "\nContact someone@" + "gmail.com\n")),
        ("link broken from the command's own folder", _edit("commands/paid-search-analyst.md", lambda t: t + "\n[analyst](references/analyst.md)\n")),
        ("absolute link", _edit("README.md", lambda t: t + "\n[hosts](/etc/hosts)\n")),
        ("broken link in a reference", _edit("references/analyst.md", lambda t: t + "\n[gone](missing-file.md)\n")),
        ("old layout path", _edit("README.md", lambda t: t + "\nSee ./skills/paid-search-intelligence/SKILL.md\n")),
        ("command invokes the wrong role", _edit("commands/paid-search-pm.md", lambda t: t.replace("as the Product Manager", "as the Analyst"))),
        ("command without frontmatter", _write("commands/paid-search-crisis.md", "Use the `paid-search-intelligence` skill crisis protocol on: $ARGUMENTS\n")),
        ("extra command file", _write("commands/paid-search-extra.md", "---\ndescription: x\nargument-hint: \"[x]\"\n---\nUse `paid-search-intelligence` on $ARGUMENTS\n")),
        ("eval case with wrong types", _json("evals/cases.json", lambda d: d["cases"][0].update({"requirements": "anything", "prohibitions": 7}))),
        ("eval case with an unknown category", _json("evals/cases.json", lambda d: d["cases"][0].update({"category": "data_truthh"}))),
        ("eval case with a bad rule reference", _json("evals/cases.json", lambda d: d["cases"][0].update({"rule_refs": ["Z9"]}))),
        ("duplicate eval prompts", _json("evals/cases.json", lambda d: d["cases"].append(dict(d["cases"][0], id="copy")))),
        ("only analyst eval cases", _json("evals/cases.json", lambda d: d.update({"cases": [c for c in d["cases"] if c["role"] in ("analyst", "any")]}))),
        ("JUDGE.md ignores the rubric", _write("evals/JUDGE.md", "# Evaluation protocol\n\n" + "Score each output from 1 to 5 on fit, fidelity and restraint. " * 30)),
        ("plugin version not bumped", _json(".claude-plugin/plugin.json", lambda d: d.update({"version": "0.0.1"}))),
        ("plugin author of the wrong type", _json(".claude-plugin/plugin.json", lambda d: d.update({"author": "IvaTech"}))),
        ("license mismatch", _json(".claude-plugin/plugin.json", lambda d: d.update({"license": "Proprietary"}))),
        ("plugin declares a missing path", _json(".claude-plugin/plugin.json", lambda d: d.update({"commands": "./cmds/"}))),
        ("reserved marketplace name", _json(".claude-plugin/marketplace.json", lambda d: d.update({"name": "claude-code-plugins"}))),
        ("marketplace renamed but README not updated", _json(".claude-plugin/marketplace.json", lambda d: d.update({"name": "renamed-marketplace"}))),
        ("marketplace entry points nowhere", _json(".claude-plugin/marketplace.json", lambda d: d["plugins"].append({"name": "ghost", "source": "./does-not-exist"}))),
        ("emptied README", _write("README.md", "# Paid Search Intelligence\n")),
    ]


def self_test(root: Path) -> int:
    files = repo_files(root)
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean"
        for rel in files:
            (clean / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, clean / rel)
        bad = [label for label, ok, _ in validate(clean) if not ok]
        print(f"{'PASS' if not bad else 'FAIL'}  unmodified copy passes" + (f"  -> {bad}" if bad else ""))
        failures += bool(bad)
        cases = mutations()
        for i, (name, apply) in enumerate(cases):
            work = Path(tmp) / f"m{i}"
            shutil.copytree(clean, work)
            apply(work)
            caught = [label for label, ok, _ in validate(work) if not ok]
            print(f"{'PASS' if caught else 'FAIL'}  rejects: {name}" + (f"  ({caught[0][:70]})" if caught else "  -> NOT DETECTED"))
            failures += not caught
    print()
    print(f"Self-test: {len(cases) + 1 - failures} of {len(cases) + 1} checks behaved as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = Path(args[0]).resolve() if args else Path(__file__).resolve().parent.parent
    sys.exit(self_test(base) if "--self-test" in sys.argv else report(validate(base)))
