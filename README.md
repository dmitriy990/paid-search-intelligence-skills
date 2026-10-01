# Paid Search Intelligence

`paid-search-intelligence` is an Agent Skill that runs paid-search work as three roles on one shared set of rules: Analyst, Optimizer and Product Manager. It works only from Google Ads and GA4 data in BigQuery, loaded by the BigQuery Data Transfer Service. It never claims to see the Google Ads or GA4 interfaces, treats BigQuery as read-only by default, and keeps personal data out of its output. To install it:

```bash
npx skills add dmitriy990/paid-search-intelligence-skills
```

Then pick a role:

```txt
/paid-search-intelligence analyst why did CPA rise last week?
/paid-search-intelligence optimizer turn this search-term audit into a change set
/paid-search-intelligence pm write the measurement spec for qualified-lead imports
/paid-search-intelligence crisis conversions fell to zero yesterday
```

Without a role word it infers the role from the request, and asks one question if it cannot.

| Role | Answers | Typical output |
|---|---|---|
| **Analyst** | What happened, why, how big, how sure? | Analytical memos, finding cards, search-term audits, experiment read-outs |
| **Optimizer** | What exactly should change in Google Ads, and how will we know it worked? | Change sets (with Google Ads Editor CSV), experiment briefs, alert specs |
| **Product Manager** | Which outcomes matter and what do we build, fix or measure next? | Metric tree, tracking spec, Jira tickets, decision records |

On first use in a dataset the Analyst runs a data inventory (tables, freshness, gaps, account time zone and currency) before any analysis. Every answer states the "data complete through" date, a confidence level and what you need to do next. This is instruction version **v1.0 (2026-10-01)**.

## Requirements

A BigQuery tool in the session (an MCP server or similar) with read access to your Ads and GA4 transfer datasets. The skill bundles no connector and no credentials. The least-privilege roles it recommends are BigQuery Data Viewer on the datasets plus Job User on the billing project.

## Other ways to install

**Claude Code plugin marketplace**

```bash
claude plugin marketplace add dmitriy990/paid-search-intelligence-skills
```

```bash
claude plugin install paid-search-intelligence@ivatech-paid-search
```

As a plugin, the skill and commands are prefixed with the plugin name.

**Manual copy**

```bash
git clone https://github.com/dmitriy990/paid-search-intelligence-skills.git
mkdir -p ~/.claude/skills/paid-search-intelligence
cp -R paid-search-intelligence-skills/SKILL.md paid-search-intelligence-skills/references ~/.claude/skills/paid-search-intelligence/
```

**Claude.ai or Cowork:** zip the same `SKILL.md` and `references/` inside a `paid-search-intelligence/` folder and upload it as a custom skill. The session still needs a BigQuery connector.

## Role commands

The skill works without these. Copy them if you prefer one command per role:

```bash
cp commands/*.md ~/.claude/commands/
```

That gives `/paid-search-analyst`, `/paid-search-optimizer`, `/paid-search-pm` and `/paid-search-crisis`.

## What is in the repo

```txt
SKILL.md                     router: roles, precedence, hard rules, load order
references/                  the full instructions: Parts A-E and the SQL appendix
commands/                    optional /paid-search-* wrappers, one per role
evals/cases.json             synthetic behavioural cases on data truth, privacy and role limits
evals/JUDGE.md               protocol for comparing runs
scripts/validate_package.py  required files, budgets, links, commands, evals, secrets
.claude-plugin/              plugin and marketplace manifests
```

`SKILL.md` stays under 1,500 words and each role loads at most 5,000 words (router, shared rules and that role's file). The evals are cases and a judging protocol, not an automated test run. The validator runs in CI on every push:

```bash
python3 scripts/validate_package.py
```

## Update

- **Users, skills CLI:** `npx skills update`.
- **Users, plugin install:** `claude plugin update paid-search-intelligence@ivatech-paid-search`. Auto-update is off by default; each user can enable it under **Marketplaces** in `/plugin`.
- **Maintainers:** a plugin release reaches users only when the version changes. Set the same version in the `SKILL.md` frontmatter and `.claude-plugin/plugin.json`, run the validator, then push and tag. When you change a rule, also update the instruction version header in `SKILL.md`.

## License

MIT, see [LICENSE](LICENSE).
