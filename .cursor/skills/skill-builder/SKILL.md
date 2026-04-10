---
name: skill-builder
description: >
  Build a production-quality SKILL.md from scratch based on project experience and domain
  knowledge. Use after completing a project or workflow and wanting to capture that expertise
  as a reusable agent skill. Enforces agentskills.io standards while personalizing output to
  the user's stack, conventions, and communication style. Also use to refactor or upgrade an
  existing skill that feels incomplete or inconsistent.
  Trigger phrases: "create a skill", "make a new skill", "build a skill from this", "turn this
  into a skill", "save this workflow as a skill", "extract skill from project", "document this
  as a skill", "tạo skill mới", "viết skill từ dự án này".
license: MIT
metadata:
  author: while-linhhq
  version: '1.0'
  tags: meta, skill-creation, agentskills, workflow, template
---

# Skill Builder

## Purpose

This skill converts tacit knowledge — gained from completing real projects — into a structured,
validated `SKILL.md` that any agent can discover and follow consistently.

**What it produces:**
- A `SKILL.md` file that passes `agentskills validate` with zero errors
- Optionally, a `references/` file for content that would bloat the main file
- Always includes a copy of `references/template.md` as a blank starter for future skills

**When NOT to use this skill:**
- User wants to edit only a small section of an existing skill → edit directly
- User wants to generate executable scripts or code → those belong in `scripts/` separately
- User cannot describe what the skill should do at all → see Stop Conditions first

---

## Workflow

### Step 1 — Intent Clarification

Ask the user for context before writing anything. Extract from prior conversation if possible.

| Question | Why |
|---|---|
| What project/workflow does this skill capture? | Defines the domain scope |
| What did you keep explaining to the agent manually? | Reveals core value |
| Who uses this — just you, team, or public? | Affects personalization depth |
| Any tech stack or tool constraints? | Fills `compatibility` field |
| Preferred output language (Vietnamese/English)? | Skill body must match |

Skip questions already answered. Never ask redundantly.

---

### Step 2 — Name the Skill

Pick a name satisfying **all**:
- 1–64 chars, lowercase, hyphens only, no leading/trailing/consecutive hyphens (`--`)
- Describes the domain, not the action

**Naming patterns:**

| Pattern | Example |
|---|---|
| Single domain | `code-review`, `api-design` |
| Tool + verb | `prisma-migration`, `docker-deploy` |
| Verb + noun | `build-changelog`, `write-spec` |
| Stack + concern | `nextjs-routing`, `fastapi-endpoint` |

---

### Step 3 — Write the Description (Most Critical)

Agents read ONLY this field to decide whether to activate the skill.

**Formula:**
```
[Primary action] [domain/output] [use cases].
Use when [trigger scenarios].
Trigger phrases: "[phrase1]", "[phrase2]", "[phrase3]", "[Vietnamese phrase]".
```

**Requirements:**
- Max 1024 chars
- Min 3 trigger phrases (include both English and Vietnamese if user is bilingual)
- Include domain keywords agents can match semantically

---

### Step 4 — Structure the Body

Always include these 7 sections in order:

| # | Section | Minimum content |
|---|---|---|
| 1 | `## Purpose` | What it does, what it produces, when NOT to use |
| 2 | `## Workflow` | Numbered steps, verb-first, decision tables |
| 3 | `## Examples` | ≥2 examples — one complete, one edge case or failure |
| 4 | `## Anti-pattern` | ≥3 items, each with explanation and fix |
| 5 | `## Stop Conditions` | ≥3 named conditions with specific triggers |
| 6 | `## Success Criteria` | Measurable gates grouped by category |
| 7 | `## Checklist` | Checkbox list, self-referential, grouped |

**Additional `##` sections (optional):** Beyond the seven required sections, add **any** extra top-level `## …` headings the domain needs — there is no closed list. Name them so agents can scan quickly (e.g. `## Prerequisites`, `## Tooling`, `## Security Notes`, `## Rollback`). Place them where they read best (often after `## Checklist`, or earlier when context must come before a step). Do **not** drop or rename the seven table sections; they must still appear once each in the same relative order as above. Examples often used:
- `## Output Format` — strict output shape
- `## References` — on-demand docs under `references/`

---

### Step 5 — Personalize

Embed user-specific context:

- **Tech stack**: exact versions if provided (`Next.js 14.2`, `Python 3.12`)
- **Naming conventions**: camelCase, kebab-case, snake_case — mirror user's codebase
- **Output format**: match user's preferred style (table vs bullets vs prose)
- **Tone**: terse/formal/casual — match how the user types
- **Domain vocab**: use the user's own terms, never rename their concepts
- **Trigger phrases**: include how the user ACTUALLY types requests (check chat history)

---

### Step 6 — Write and Size

```
Rule: body ≤ 250 lines.
If content exceeds 300 lines → move reference material to references/detail.md
                             → link from SKILL.md: "See references/detail.md for X"
```

Writing rules:
- Every instruction starts with an action verb ("Read", "Ask", "Write", "Check", "Run")
- Bold all critical constraints
- Use code blocks with language tags for ALL code and YAML
- Use tables for comparisons, not paragraph prose

---

### Step 7 — Validate

```bash
pip install -q skills-ref && agentskills validate /path/to/skill-name/
```

Fix all errors before proceeding. See Anti-pattern section for common failures.

---

### Step 8 — Package and Deliver

| Contents | Deliver as |
|---|---|
| `SKILL.md` only | Share the `.md` file directly |
| `SKILL.md` + any bundled files | Zip the skill directory → share `.zip` |

Never share as a raw directory path or `.tar` archive.

---

## Examples

### Example A — Well-Formed Skill (Complete)

**Context:** User finished building a REST API with FastAPI and wants to capture the pattern.

**Good frontmatter:**
```yaml
---
name: fastapi-endpoint
description: >
  Build production-ready FastAPI endpoints with Pydantic validation, dependency injection,
  and standardized error handling. Use when creating new routes, adding request validation,
  or structuring response schemas for a Python backend.
  Trigger phrases: "create endpoint", "add API route", "new FastAPI route",
  "build REST endpoint", "thêm endpoint mới".
license: MIT
metadata:
  author: while-linhhq
  version: '1.0'
  tags: fastapi, python, api, rest
---
```

**Why this works:**
- Description answers WHAT + WHEN in 3 sentences
- 5 trigger phrases including one Vietnamese phrase
- Name is domain-descriptive, not action-descriptive
- Metadata is properly nested under `metadata:`

---

### Example B — Narrow Scope (Single-Purpose)

**Context:** User wants a skill just for writing Git commit messages in their team's style.

**Approach:**
- Name: `commit-message` — narrow, single-purpose ✅
- Description: explicitly states the team convention (Conventional Commits + Jira ID prefix)
- Workflow: 3 steps max — no over-engineering for a simple task
- Checklist: 5 items max

**Key lesson:** A 80-line focused skill always outperforms a 600-line bloated skill.
Single responsibility → faster agent discovery → more consistent output.

---

### Example C — Bad Skill (What to Avoid)

```yaml
---
name: my-skill
description: helps with coding tasks when needed
---
# My Skill
Do things well and follow best practices.
```

**Problems:**
- `my-skill` is non-descriptive — no agent will discover this
- Description has zero trigger phrases and zero domain keywords
- Body has no actionable steps — pure vague prose
- Will never be triggered correctly by any agent

---

## Anti-pattern

### ❌ Vague Description Without Trigger Phrases
Writing `"Helps with coding tasks"` gives agents nothing to match against.
**Fix:** Always include 3+ trigger phrases in quotes inside the description field.

### ❌ Top-Level Custom Frontmatter Fields
```yaml
version: '1.0'    # ← INVALID — causes agentskills validate to fail
tags: python      # ← INVALID
```
**Fix:** Nest all custom fields under `metadata:`:
```yaml
metadata:
  version: '1.0'
  tags: python
```

### ❌ Content Before the Opening `---`
Any title, blank line, or comment before `---` causes validation failure.
**Fix:** The very first bytes of the file must be `---`. No exceptions.

### ❌ One Skill for Everything
Cramming API design + testing + deployment + docs into one file.
**Fix:** Split into composable, focused skills. Each should do one thing well.

### ❌ Instructions Without Examples
Steps alone are not enough — agents need input/output anchors.
**Fix:** Every workflow must have ≥2 examples. At least one should show a failure case.

### ❌ Secrets in the Skill File
Hardcoding API keys, passwords, or private URLs inside SKILL.md.
**Fix:** Never put credentials in skill files. Reference environment variables instead.

### ❌ Writing for Humans Instead of Agents
Phrases like "Remember to..." or "It's important that..." underperform with agents.
**Fix:** Use direct imperative: "Always validate input before processing."

---

## Stop Conditions

Halt immediately and ask the user before writing any content if:

1. **No domain defined** — User says "make me a skill" without describing the project,
   workflow, or what problem the skill should solve. A skill with no domain cannot be named,
   described, or structured correctly.

2. **Scope too large for one file** — The requested skill covers 3+ unrelated domains
   (e.g., "code review + deployment + documentation"). Ask: "Should we create separate
   skills for each, or pick the most important one first?"

3. **Secrets detected in input** — User's description, examples, or pasted code contains
   API keys, passwords, database credentials, or private URLs. Flag this explicitly and
   ask them to sanitize before continuing.

4. **Conflicting requirements** — User describes constraints that contradict each other
   (e.g., "no internet access" but the workflow requires fetching live docs). Clarify
   which constraint takes priority.

5. **Success definition missing** — User cannot say what "good output" looks like from
   this skill. Without this, the Success Criteria section will be empty or invented.
   Ask: "What does a successful run of this skill look like to you?"

---

## Success Criteria

A skill is considered complete and ready to deliver when ALL pass:

### Structural (Non-negotiable)
- [ ] File starts with `---` on line 1, no blank lines before it
- [ ] `name` is valid: lowercase, 1–64 chars, hyphens only, matches directory name
- [ ] `description` is 1–1024 chars, includes trigger phrases, describes WHAT + WHEN
- [ ] Body is ≤500 lines OR overflow is split to `references/`
- [ ] `agentskills validate` exits with code 0, zero errors

### Content Quality
- [ ] All 7 required sections present and non-empty
- [ ] Every workflow step starts with an action verb
- [ ] ≥2 examples: one complete, one edge/failure case
- [ ] ≥3 anti-patterns with explanations and fixes
- [ ] ≥3 stop conditions with specific triggers (not vague "if unclear")
- [ ] Success Criteria are measurable (checkboxes, not prose)
- [ ] Checklist is grouped and self-referential

### Personalization
- [ ] Trigger phrases match how the user actually types requests
- [ ] Tech stack named explicitly if applicable
- [ ] User's naming conventions reflected in examples
- [ ] Language of body matches user's language (Vietnamese or English)

### Deliverable
- [ ] Packaged correctly (`.md` solo or `.zip` bundled)
- [ ] User can install and use the skill immediately without modification

---

## Checklist

Run through every item before sharing the final file.

**Frontmatter**
- [ ] `---` is the literal first line, byte 1 of the file
- [ ] `name` matches the parent directory name exactly
- [ ] `description` has ≥3 trigger phrases in quotes
- [ ] No illegal top-level fields outside: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`
- [ ] Custom data is nested under `metadata:`

**Body — Required Sections**
- [ ] `## Purpose` — includes what it does, what it produces, and when NOT to use
- [ ] `## Workflow` — all steps numbered, verb-first, no vague steps
- [ ] `## Examples` — ≥2 examples, each with "Why this works" or failure explanation
- [ ] `## Anti-pattern` — ≥3 entries, each with ❌ label + explanation + fix
- [ ] `## Stop Conditions` — ≥3 named, specific conditions (not "if unclear, ask")
- [ ] `## Success Criteria` — grouped checkboxes covering structure, quality, personalization
- [ ] `## Checklist` — this section itself is filled (not the template placeholder)

**Quality Gates**
- [ ] No hardcoded secrets, credentials, or private URLs
- [ ] No vague instructions ("do it well", "follow best practices", "be careful")
- [ ] All code and YAML use fenced blocks with language tags
- [ ] Body is ≤500 lines (count with `wc -l SKILL.md`)

**Validation & Delivery**
- [ ] `agentskills validate` passes with zero errors
- [ ] File packaged as `.md` (solo) or `.zip` (bundled)
- [ ] `references/template.md` included if this is a skill-builder delivery
