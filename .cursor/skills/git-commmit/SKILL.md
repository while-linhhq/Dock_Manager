---
name: git-commmit
description: >
  Draft Git commit messages using Conventional Commits with a fixed emoji per type, optional
  scope, and optional body/footer. Use when the user asks to commit, write a message, push, or
  normalize commit history per Dock_Manager rules in .cursor/rules/git-workflow.mdc.
  Trigger phrases: "commit code", "git commit", "conventional commit", "commit message",
  "đặt commit", "commit có emoji", "chuẩn commit".
license: MIT
metadata:
  author: while-linhhq
  version: '1.0'
  tags: git, commit, conventional-commits, emoji, workflow
---

# Conventional Commit + Emoji

## Purpose

Guide the agent (and the user) to write a **single-line subject** plus optional **body/footer**
that match `.cursor/rules/git-workflow.mdc`, with **one emoji per `type`** at the start of the
subject for faster scanning in Git history.

**Output:** A commit message string ready for `git commit -m "..."` or multiple `-m` flags for
body/footer.

**Do not use this skill when:** the user only needs a quick amend without caring about format;
or the team **forbids emoji** in the subject — follow team rules and omit emoji.

## Workflow

1. **Read** the change set (`git status`, `git diff --staged`) and identify **one** primary
   logical change per commit.
2. **Pick `type`** from the Types table (step 4); if unclear, prefer `refactor` or `chore`
   instead of mislabeling `feat` / `fix`.
3. **Pick `scope`** (module, package, area) — lowercase, short, no spaces; omit parentheses
   when there is no clear scope.
4. **Apply emoji** from the Emoji table; **exactly one emoji** at the start of the subject,
   then a single space, then the Conventional Commits portion.
5. **Write the short description** after the colon: imperative mood in English (add, fix,
   update), **no** trailing period, keep the full subject around ~72 characters when feasible.
6. **Add body** when you must explain why or impact; **footer** for `Closes #123`,
   `BREAKING CHANGE:`, etc., per PR rules in `git-workflow.mdc`.
7. **Verify** no secrets are included; do not stage `.env` / `node_modules`; run tests when
   project rules require before committing.

### Subject format (with emoji)

```text
<emoji> <type>(<scope>): <short description>
```

Without scope:

```text
<emoji> <type>: <short description>
```

### Types (project)

| `type` | When to use |
|--------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no logic change |
| `refactor` | Restructure without feat/fix |
| `test` | Add or fix tests |
| `chore` | Build, tooling, dependencies |
| `perf` | Performance improvement |

### Emoji (default — keep stable in this repo)

| `type` | Emoji |
|--------|--------|
| `feat` | ✨ |
| `fix` | 🐛 |
| `docs` | 📝 |
| `style` | 💄 |
| `refactor` | ♻️ |
| `test` | ✅ |
| `chore` | 🔧 |
| `perf` | ⚡️ |

If the user requests a **different Gitmoji** (e.g. breaking `💥`), document it in the body or
use a `BREAKING CHANGE:` footer per Conventional Commits 1.0.

## Examples

### Complete example (rules + emoji)

**Input:** Add JWT refresh token support in the auth module.

**Output:**

```text
✨ feat(auth): add JWT refresh token support
```

**Why it works:** One type, clear scope, imperative English, emoji matches `feat`, aligns with
`git-workflow.mdc` examples (with emoji added).

### Failure / edge case

**Input:** Fix a small UI alignment bug, but the agent labels it `feat` because a button moved.

**Wrong:** `✨ feat(ui): fix button alignment` — wrong type (`feat` vs `fix`).

**Right:** `🐛 fix(ui): correct button alignment on mobile`

**Why:** `fix` + 🐛 reflects a bugfix, not a new feature.

## Anti-pattern

### ❌ Multiple sentences or multiple intents in one subject

**Fix:** Split commits or move secondary detail to the body.

### ❌ Two emojis or emoji inside `type(scope):`

Bad: `feat✨(auth): add token`

**Fix:** One emoji at the **start** only: `✨ feat(auth): add token`

### ❌ Non-English subject when team rules use imperative English

**Fix:** Keep the subject in English per `git-workflow.mdc`; put localized explanation in the
body only if the team allows it.

## Stop Conditions

1. **Primary change unclear** — no diff or too many unrelated topics: ask whether to split
   commits or which scope to use.
2. **Secrets or forbidden files staged** — stop; do not suggest a message until removed from
   the index.
3. **Team rules conflict** (e.g. "no emoji"): follow team rules, drop emoji, tell the user.

## Success Criteria

### Structure

- [ ] Subject starts with exactly one emoji from the table (or an agreed Gitmoji variant).
- [ ] Text after the emoji matches `type(scope): description` or `type: description`.
- [ ] No trailing period on the subject; do not shout the description in all caps.

### Quality

- [ ] `type` matches the project table; `scope` is short and meaningful.
- [ ] Aligns with at least one pattern in `git-workflow.mdc` (emoji added).

### Communication

- [ ] User gets a copy-paste string plus optional full `git commit` example if they ask.

## Checklist

**Before proposing a message**

- [ ] Reviewed diff / list of staged files.
- [ ] Picked correct `type` + matching emoji.
- [ ] Subject is short, imperative English (unless user/team overrides).

**Before commit (project)**

- [ ] Do not commit `.env`, secrets, or `node_modules`.
- [ ] PR/issue: add `Closes #…` footer when preparing a PR if rules require it.

**After writing the message**

- [ ] User can run `git commit -m "…"` or split `-m` for body/footer.
