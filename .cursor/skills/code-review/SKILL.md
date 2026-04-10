---
name: code-review
description: >
  Perform thorough code reviews covering bugs, security vulnerabilities, performance, 
  maintainability, and best practices. Use when the user asks to review, audit, inspect, 
  check, QA, or evaluate code quality — for any language or framework. Produces structured 
  review reports with severity levels (critical, warning, suggestion), inline code references, 
  and concrete fix recommendations. Also handles PR reviews, architecture assessments, 
  and incremental reviews when the user shares a diff or patch.
---

# Code Review Skill

## When to Use This Skill

Load this skill when the user asks you to:

- Review, audit, inspect, or evaluate source code
- Check code quality, readability, or maintainability
- Find bugs, logic errors, or potential runtime issues
- Identify security vulnerabilities (injection, XSS, CSRF, etc.)
- Assess performance bottlenecks or inefficiencies
- Review a pull request (PR), diff, or patch
- Enforce coding standards or style guidelines
- Validate error handling, edge cases, or test coverage
- Suggest refactors or architectural improvements

Trigger phrases: *"review this code"*, *"check my code"*, *"audit this file"*, *"what's wrong with this"*, *"can you QA this"*, *"look over my PR"*, *"find bugs in"*, *"is this code safe?"*

---

## Instructions

### Step 1 — Gather Context

Before reviewing, clarify the following if not already provided:

| Question | Why it matters |
|---|---|
| Language / framework? | Determines applicable idioms and security patterns |
| Purpose of the code? | Helps evaluate design decisions |
| Target environment? | Server vs. client vs. embedded changes risk surface |
| Specific concerns? | User may want security-only, performance-only, etc. |
| Coding standard/style guide? | Avoids flagging intentional style choices |

If the user pastes code directly, infer as much as possible before asking.

---

### Step 2 — Read and Understand the Code

1. Read the entire file or diff before writing any feedback.
2. Identify the module's responsibility and data flow.
3. Note dependencies, external calls, and I/O boundaries.
4. Understand the happy path before looking for edge cases.

---

### Step 3 — Analyse Across All Dimensions

Review the code across **six dimensions** in this order:

#### 3a. Correctness & Logic
- Off-by-one errors, incorrect conditionals, wrong operator precedence
- Infinite loops or unreachable code
- Incorrect type coercion or implicit casting
- Race conditions in concurrent code
- Incorrect algorithm or data structure choice

#### 3b. Security
- Injection vulnerabilities (SQL, command, LDAP, XPath)
- Cross-site scripting (XSS) and CSRF
- Insecure deserialization
- Hard-coded credentials, secrets, or API keys
- Improper authentication / authorization checks
- Sensitive data exposure (logging PII, unencrypted storage)
- Dependency vulnerabilities (flag outdated or known-vulnerable packages)
- Cryptographic weaknesses (MD5, SHA1, weak random, ECB mode)

#### 3c. Performance
- Unnecessary loops inside loops (O(n²) where O(n) is achievable)
- Repeated expensive operations that can be cached or memoized
- N+1 query patterns in database access
- Blocking I/O on hot paths
- Excessive memory allocation or large object creation in tight loops
- Missing indexes on frequently queried fields (if DB schema is visible)

#### 3d. Maintainability & Readability
- Unclear variable/function names that require mental decoding
- Functions longer than ~40 lines or doing more than one thing (SRP)
- Magic numbers or strings without named constants
- Deep nesting (> 3 levels) that can be flattened
- Missing or outdated comments on non-obvious logic
- Duplicated code that should be extracted into a shared utility

#### 3e. Error Handling & Resilience
- Unhandled exceptions or promise rejections
- Silent error swallowing (`catch {}` with no logging or re-throw)
- Missing input validation or boundary checks
- Assumptions about external service availability
- Incomplete rollback on partial failures (especially in transactions)

#### 3f. Test Coverage (if tests are present or requested)
- Missing unit tests for critical paths
- Tests that only cover the happy path
- Flaky tests (time-dependent, order-dependent, network-dependent)
- Assertions that don't actually verify meaningful behaviour
- Missing mocks for external dependencies

---

### Step 4 — Assign Severity Levels

Tag every finding with one of these levels:

| Level | Icon | Meaning |
|---|---|---|
| Critical | 🔴 | Must fix before shipping — data loss, security breach, crash |
| Warning | 🟡 | Should fix — likely causes bugs or degrades quality |
| Suggestion | 🔵 | Nice to have — style, readability, minor optimisation |
| Praise | ✅ | Explicitly acknowledge good patterns found |

---

### Step 5 — Write the Review Report

Structure the output as follows:

```
## Code Review: <filename or description>

### Summary
<2–4 sentence overview: what the code does, overall quality, main themes in findings>

### Findings

#### 🔴 Critical

**[C1] <Short title>**
- **Location**: `filename.ext`, line(s) XX–YY
- **Issue**: <Clear description of the problem>
- **Impact**: <What can go wrong if not fixed>
- **Fix**:
  ```<language>
  // suggested fix code
  ```

#### 🟡 Warning

**[W1] <Short title>**
- **Location**: ...
- **Issue**: ...
- **Recommendation**: ...

#### 🔵 Suggestion

**[S1] <Short title>**
- **Location**: ...
- **Idea**: ...

#### ✅ Praise

- <Specific thing done well and why it's good>

---

### Overall Score

| Dimension | Score |
|---|---|
| Correctness | X / 10 |
| Security | X / 10 |
| Performance | X / 10 |
| Maintainability | X / 10 |
| Error Handling | X / 10 |

**Overall: X / 10**

### Next Steps

1. <Most important fix>
2. <Second most important>
3. <Optional improvement>
```

---

### Step 6 — Incremental Review (Diff / PR mode)

When the user provides a diff or PR link:

1. Focus only on changed lines (do not re-review unchanged context).
2. Check that the change doesn't introduce regressions in adjacent code.
3. Verify the PR description matches what the code actually does.
4. Note if tests were updated in proportion to logic changes.
5. Use the same report format but prefix findings with `[NEW]`, `[MODIFIED]`, or `[ADJACENT]`.

---

### Step 7 — Follow-up

After delivering the review:

- Offer to explain any finding in more detail.
- Offer to write the fix for any Critical or Warning item.
- If the user applies fixes, offer a re-review of the updated code.
- If the user wants a recurring review workflow, suggest setting up a cron or CI check.

---

## Examples

### Example 1 — Python SQL Injection

**User input:**
```python
def get_user(username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return db.execute(query)
```

**Expected output excerpt:**
> **[C1] SQL Injection via f-string interpolation**
> - **Location**: `app.py`, line 2
> - **Issue**: User-controlled `username` is interpolated directly into the SQL query string. An attacker can pass `' OR '1'='1` to dump the entire table or `'; DROP TABLE users; --` to destroy data.
> - **Impact**: Full database compromise, data exfiltration, or destruction.
> - **Fix**:
>   ```python
>   def get_user(username):
>       query = "SELECT * FROM users WHERE username = %s"
>       return db.execute(query, (username,))
>   ```

---

### Example 2 — JavaScript N+1 Query

**User input:**
```js
const posts = await Post.findAll();
for (const post of posts) {
  post.author = await User.findById(post.userId);
}
```

**Expected output excerpt:**
> **[W1] N+1 query pattern — O(n) database calls**
> - **Location**: `feed.js`, lines 2–4
> - **Issue**: For every post, a separate `User.findById` query is executed. With 100 posts this makes 101 DB round-trips.
> - **Recommendation**: Use an eager-load (JOIN) or batch fetch:
>   ```js
>   const posts = await Post.findAll({ include: [{ model: User, as: 'author' }] });
>   ```

---

### Example 3 — No issues found

If the code is genuinely clean:

> **Summary**: The module is well-structured, handles errors correctly, and uses parameterised queries throughout. No critical or warning issues found.
>
> **✅ Praise**
> - Uses `finally` blocks to guarantee resource cleanup — good resilience pattern.
> - Input validation is exhaustive and returns descriptive error messages.
>
> **Overall: 9 / 10**

---

## Output Format Rules

- Always use fenced code blocks with language tags for all code snippets.
- Always reference specific line numbers when available.
- Never say "this code is bad" — be precise and constructive.
- If the code is in a language you're uncertain about, state your confidence level upfront.
- Keep the Summary under 5 sentences.
- If there are more than 10 findings, group minor suggestions into a single "Minor notes" bullet list to avoid overwhelming the user.
