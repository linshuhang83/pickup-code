# English README implementation plan

> **For AI implementers:** Required sub-skill: use `executing-plans` to execute this plan task by task. Track each step with Markdown checkboxes.

**Goal:** Replace the repository-root README with accurate English documentation for Pickup Code.

**Architecture:** This is a documentation-only change. `README.md` remains the GitHub landing page and describes the existing Mac-local backend, static PWA frontend, and Vercel/Tailscale deployment without changing runtime behavior.

**Tech stack:** Markdown, Python pytest verification, Git.

---

## Files

- Modify: `README.md` — English repository landing page and operating guide.
- Reference: `web/vercel.json` — deployed API rewrite hostname and cache/security headers.
- Reference: `server/main.py` — documented API access-token behavior.
- Reference: `server/tests/` — verification command and current test suite.

### Task 1: Replace the README with the English guide

**Files:**

- Modify: `README.md`

- [x] **Step 1: Inspect current implementation facts**

Run: `rg -n 'QJK_TOKEN|@app\.(get|post|put|delete)' server/main.py && sed -n '1,160p' web/vercel.json`

Expected: the access-token behavior and `/api/:path*` Tailscale Funnel rewrite are available as documentation sources.

- [x] **Step 2: Rewrite `README.md` in English**

Include these sections in this order: title and summary; architecture diagram; requirements; quick start; macOS Full Disk Access; iMessage forwarding prerequisites; feature overview; Bark notifications; access-token use; phone/PWA use; GitHub + Vercel + Tailscale Funnel deployment; test command; technology stack; security guidance.

Use the following required security guidance:

```markdown
Never commit `QJK_TOKEN`, Bark keys, `data/`, `~/Library/Messages/chat.db`, or real SMS contents.
```

State the verified test command exactly:

```bash
.venv/bin/python -m pytest server/tests/ -q
```

- [x] **Step 3: Validate Markdown and documented deployment configuration**

Run: `python3 -m json.tool web/vercel.json >/dev/null && git diff --check && rg -n 'QJK_TOKEN=|api\.day/[A-Za-z0-9]{12,}' README.md`

Expected: JSON and whitespace checks exit 0; the final search prints no secret-like literals.

- [x] **Step 4: Run the regression suite**

Run: `'/Users/linshuhang/Desktop/AI coding/取件码/.venv/bin/python' -m pytest server/tests/ -q`

Expected: `99 passed`; the existing Starlette deprecation warning is allowed.

- [ ] **Step 5: Show the staged summary, commit, and push**

Run: `git diff --stat && git status --short`

Expected: only `README.md` and this approved plan document are candidates for commit; do not stage any token, database, or user-owned untracked files.

After showing the summary, create the English README commit with:

```bash
git add README.md docs/superpowers/plans/2026-08-25-english-readme.md
git commit -m "docs: add English README"
git push origin HEAD:main
```

Expected: the GitHub `main` branch receives the README update, which triggers Vercel's static-site deployment.
