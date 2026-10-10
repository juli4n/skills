---
name: this-week-in-substrate
description: Write the "This Week in Agent Substrate" report, a single self-contained HTML page summarizing what happened in agent-substrate/substrate over a period (merged PRs, bug fixes, features, breaking changes, releases, notable discussions, new contributors). Use when asked for a weekly summary, newsletter, digest or recap of Substrate activity since a given date.
---

# This Week in Agent Substrate

Produces one self-contained HTML page (inline CSS, no external assets) for Substrate developers and users who want to keep up with the project. Paths below are relative to the directory containing this `SKILL.md`. It needs `gh` (authenticated) and `python3` with PyYAML.

## 1. Pick the window

The window is `[since, until)` in UTC dates. Use what the user gives; by default `until` is today and `since` is 7 days earlier. Unless the user names a location, write everything to `~/this-week-in-substrate/<until>/`.

## 2. Gather

```
python3 -I scripts/gather.py --since <since> --until <until> --out <dir>/data.json
```

It collects:

- merged PRs, each with a `section` computed from `.github/release.yml` the same way the release notes are
- issues opened and closed
- the most active issue and PR threads in the window, with their recent comments
- releases
- contributors, and first-time contributors (no merged PR before `since`)

## 3. Read the data

Read all of `data.json`, in chunks if needed. For any PR you plan to feature that has a thin body, open it with `gh pr view <n> --repo agent-substrate/substrate`. Do the same with `gh issue view` for any issue you plan to feature.

## 4. Write `<dir>/report.json`

The schema is in the docstring at the top of `scripts/render.py`. The renderer adds these sections automatically, so do not write them yourself:

- header and stats
- release banners
- the new-contributor and contributor lists
- a complete, collapsible list of every merged PR grouped by release-note section

Your job is the editorial part.

- **title**: `This Week in Agent Substrate` unless the user asks for another.
- **tldr**: 2–4 sentences. What a user would want to know if they read nothing else.
- **highlights**: 3–6 cards. Each is a user-visible capability, a significant behavior change, a release, or a large internal effort that reached a milestone. Combine related PRs into one card and cite them all in `refs`. In the body, say what changed and why it matters to someone running or building on Substrate, not how the code changed. Use 1–2 short paragraphs.
- **breaking**: one item per `breaking-change` PR, or per group of closely related ones. Say what users must do when they upgrade, using the PR's `breaking_note` (its "Breaking change" section). The renderer refuses to build the page if any labeled PR is missing.
  - Some PRs have a `breaking_note` but no label. Include each one that changes the public API, CRDs, flags, config, metric labels or log formats. Leave out ones that only affect contributors. The renderer warns about those it doesn't find under "breaking".
  - If a release came out in the window, start each item with **In vX.Y.Z.** or **After vX.Y.Z.**, using the release's `window_prs_in_release` and `window_prs_after_release`.
- **sections**: grouped bullets for the remaining notable changes. Use these headings, skip empty ones, and keep this order:
  - Bug fixes
  - Networking and egress
  - Security and identity
  - Observability
  - Workers and actors
  - Install, CLI and operations
  - Docs
  - Developer experience
  
  Leave out pure refactors, test-only changes, renames and dependency bumps unless they matter to users or contributors. They are still in the full list. Combine related PRs into one bullet.
- **discussions**: 2–5 threads from `threads` or `issues_opened` that readers may want to join. Good candidates are design proposals, contested trade-offs, RFC-style issues, and active issues about behavior users will notice. Summarize the question and where the discussion stands, without taking sides.
- **closing**: optional; usually omit.

Rules:

- Every claim needs a `#N` that exists in `data.json`, either inline in the text or in `refs`. Never describe a change you did not read about in the data.
- `refs` hold numbers, not strings.
- Write for readers outside the core team: name the component and the user-facing effect, and use `code` for flags, fields, commands and RPCs.
- American English. Plain, specific sentences, with no hype ("exciting", "huge", "game-changing").

## 5. Render

```
python3 -I scripts/render.py --data <dir>/data.json --report <dir>/report.json --out <dir>/index.html
```

If it reports unknown references or uncited breaking-change PRs, fix `report.json` and run it again. When it succeeds, give the user the path to `index.html`. If your environment can publish or host an HTML page, offer to do that so they have a link to share.
