# Paid Search Intelligence

`paid-search-intelligence` is an Agent Skill that runs paid-search work as three roles on one shared set of rules: Analyst, Optimizer and Product Manager. It queries only Google Ads and GA4 data in BigQuery, loaded by the BigQuery Data Transfer Service. It never claims to see the Google Ads or GA4 interfaces, treats BigQuery as read-only by default, and keeps personal data out of its output. To install it:

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

Without a role word it infers the role from the request, and asks one question if it cannot. `crisis` is a protocol that all three roles run, not a fourth role.

| Role | Answers | Typical output |
|---|---|---|
| **Analyst** | What happened, why, how big, how sure? | Analytical memos, finding cards, search-term audits, experiment read-outs |
| **Optimizer** | What exactly should change in Google Ads, and how will we know it worked? | Change sets (with a Google Ads Editor CSV when its headers can be verified), experiment briefs, alert specs |
| **Product Manager** | Which outcomes matter and what do we build, fix or measure next? | Metric tree, tracking spec, Jira tickets, decision records |

At the start of work that uses data, in a new conversation or a new dataset, the skill runs a data inventory (tables, freshness, gaps, account time zone and currency) before any analysis. It skips the inventory for requests that need no data and says so. Every substantive answer states the "data complete through" date, a confidence level and what you need to do next. Clarifying questions, approval requests and crisis updates use shorter forms.

If you paste aggregates or an export from Google Ads or GA4, the skill analyses them and labels the source as pasted by the user and not verified against BigQuery.

This is instruction version **v1.1 (2026-10-02)**.

## Requirements

To query data, the session needs a BigQuery tool (an MCP server or similar) with read access to your Ads and GA4 transfer datasets. The skill bundles no connector and no credentials. The least-privilege roles it recommends are BigQuery Data Viewer on the datasets plus Job User on the billing project.

Without a BigQuery tool the skill says so and presents no numbers of its own. It gives a plan, the queries for you to run and the aggregates to bring back.

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
```

```bash
mkdir -p ~/.claude/skills/paid-search-intelligence
```

```bash
cp -R paid-search-intelligence-skills/SKILL.md paid-search-intelligence-skills/references ~/.claude/skills/paid-search-intelligence/
```

**Claude.ai or Cowork:** zip the same `SKILL.md` and `references/` inside a `paid-search-intelligence/` folder and upload it as a custom skill. The session still needs a BigQuery connector to query data.

## Role commands

The skill works without these. Copy them if you prefer a dedicated command for each role and for the crisis protocol. The plugin install already includes them. For the other install routes the files are in the `commands/` folder of this repo, so clone it first (skip this step if you cloned it for the manual copy):

```bash
git clone https://github.com/dmitriy990/paid-search-intelligence-skills.git
```

Create the commands directory if it does not exist:

```bash
mkdir -p ~/.claude/commands
```

Copy the four files from the clone:

```bash
cp paid-search-intelligence-skills/commands/*.md ~/.claude/commands/
```

That gives `/paid-search-analyst`, `/paid-search-optimizer`, `/paid-search-pm` and `/paid-search-crisis`.

## What is in the repo

```txt
SKILL.md                     router: roles, precedence, hard rules, load order
references/                  the full instructions: Parts A-E and the SQL appendix
commands/                    optional /paid-search-* wrappers: one per role, one for the crisis protocol
evals/cases.json             synthetic behavioural cases on data truth, privacy and role limits
evals/JUDGE.md               protocol for running and judging the cases by hand
scripts/validate_package.py  required files, budgets, links, commands, evals, secrets
.claude-plugin/              plugin and marketplace manifests
```

Current sizes, each capped by the validator: `SKILL.md` is about 1,480 words (cap 1,500). One role load (the router, the shared rules and that role's file) is about 7,600 words (cap 8,200). With the SQL file it is about 10,500 words (cap 11,400). All roles together, as loaded for a chain or a crisis, are about 12,400 words (cap 13,400).

The eval cases are run by hand with [evals/JUDGE.md](evals/JUDGE.md). They are not an automated test, and the validator checks only that the cases are well formed. `evals/cases.json` holds the expected behaviour for each case, so run the cases against a copy of the skill that does not contain `evals/`. The manual copy above is such a copy.

The validator and its self-test run in CI on pushes to `main`, on version tags and on pull requests:

```bash
python3 scripts/validate_package.py
```

```bash
python3 scripts/validate_package.py --self-test
```

## Update

- **Users, skills CLI:** `npx skills update`.
- **Users, plugin install:** `claude plugin update paid-search-intelligence@ivatech-paid-search`. Auto-update is off by default; each user can enable it under **Marketplaces** in `/plugin`.
- **Maintainers:** a plugin release reaches users only when the version changes. The version lives in two files: `SKILL.md` (`metadata.version` in the frontmatter and the instruction version header) and `.claude-plugin/plugin.json`. The validator checks that they agree and that this README names the header version. Set all of them, run the validator, then push and tag.

## License

MIT, see [LICENSE](LICENSE).
