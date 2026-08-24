# English README Design

## Goal

Replace the repository-root `README.md` with a complete English README so the GitHub project is immediately understandable to English-speaking readers.

## Scope

- Rewrite only `README.md` in English.
- Describe the existing macOS iMessage monitoring, FastAPI/SQLite backend, PWA frontend, Bark notifications, access-token flow, and GitHub + Vercel + Tailscale Funnel deployment.
- State the current test result as 99 passing tests.
- Keep all commands, filenames, URLs, and configuration names accurate to the deployed project.

## Security and privacy

- Do not include `QJK_TOKEN`, Bark keys, SQLite data, iMessage database contents, real SMS samples, or personal information.
- State that secrets and local runtime data must not be committed.

## Non-goals

- No application, API, deployment, or configuration behavior changes.
- No Chinese README or secondary documentation file.

## Verification

- Check the Markdown for accurate repository paths and deployment commands.
- Run the existing full server test suite to confirm the documentation-only change leaves behavior unchanged.
