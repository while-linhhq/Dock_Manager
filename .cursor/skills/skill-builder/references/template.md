# SKILL.md Blank Template

Copy this file to `your-skill-name/SKILL.md` and fill in all `[...]` placeholders.
Remove all bracketed instructions before running `agentskills validate`.

---

```yaml
---
name: [skill-name]
description: >
  [What this skill does and what it produces].
  Use when [trigger scenarios].
  Trigger phrases: "[phrase1]", "[phrase2]", "[phrase3]".
license: MIT
metadata:
  author: [your-name]
  version: '1.0'
  tags: [tag1, tag2, tag3]
---
```

---

## Purpose

[What this skill exists to do. What output it produces. When NOT to use it.]

**What it produces:**
- [Output 1]
- [Output 2]

**When NOT to use:**
- [Case 1]
- [Case 2]

---

## Workflow

### Step 1 — [Step Name]

[Actionable instructions. Start every instruction with a verb.]

### Step 2 — [Step Name]

[Instructions...]

| Condition | Action |
|---|---|
| [Case A] | [Do this] |
| [Case B] | [Do this] |

### Step 3 — [Step Name]

```bash
# [Example command if applicable]
```

---

## Examples

### Example A — [Complete Example Name]

**Context:** [When / why this example applies]

**Input:**
```[language]
[Example input]
```

**Output:**
```[language]
[Example output]
```

**Why this works:**
[Explanation of what makes this a good example]

---

### Example B — Edge Case / Failure

**Context:** [Edge case or failure scenario]

[Describe the situation and the correct way to handle it]

**Key lesson:** [One-sentence takeaway]

---

### Example C — Bad Pattern (Optional)

```[language]
[Wrong code or config]
```

**Problems:**
- [Problem 1]
- [Problem 2]

---

## Anti-pattern

### ❌ [Anti-pattern Name]

[What it is, why it fails, what to do instead.]

**Fix:** [Correct approach]

### ❌ [Anti-pattern Name]

[Description]

**Fix:** [Correct approach]

### ❌ [Anti-pattern Name]

[Description]

**Fix:** [Correct approach]

---

## Stop Conditions

Halt and ask the user before continuing if:

1. **[Condition name]** — [Specific description of when to stop and what to ask]

2. **[Condition name]** — [...]

3. **[Condition name]** — [...]

---

## Success Criteria

The output is considered complete when ALL of the following are true:

### [Category 1 — e.g. Structural]
- [ ] [Measurable criterion]
- [ ] [Measurable criterion]

### [Category 2 — e.g. Quality]
- [ ] [Measurable criterion]
- [ ] [Measurable criterion]

### [Category 3 — e.g. Personalization]
- [ ] [Measurable criterion]

---

## Checklist

Run through every item before delivering the final file.

**[Group 1 — e.g. Frontmatter]**
- [ ] [Check item]
- [ ] [Check item]

**[Group 2 — e.g. Body Sections]**
- [ ] [Check item]
- [ ] [Check item]

**[Group 3 — e.g. Quality Gates]**
- [ ] [Check item]
- [ ] [Check item]

**[Group 4 — e.g. Validation]**
- [ ] `agentskills validate` passes with zero errors
- [ ] File packaged as `.md` (solo) or `.zip` (bundled)

---

> **Tip:** Run `wc -l SKILL.md` to count lines — keep under 500.
> If body exceeds 400 lines, move reference material to `references/detail.md` and link from SKILL.md.
