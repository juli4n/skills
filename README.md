# Agent skills

Skills for coding agents, in the [Agent Skills](https://agentskills.io) format: one folder per skill under `skills/`, each with a `SKILL.md` (YAML frontmatter with `name` and `description`, then instructions) and any helper scripts under `scripts/`. They contain nothing tool-specific.

| Skill | What it does | Needs |
|---|---|---|
| [`this-week-in-substrate`](skills/this-week-in-substrate/SKILL.md) | Writes a "This Week in Agent Substrate" report as one self-contained HTML page | `gh`, `python3` with PyYAML |

## Install

Copy a skill's folder into `~/.agents/skills/`, or into a repository's `.agents/skills/` to use it only there:

```sh
mkdir -p ~/.agents/skills
cp -r skills/this-week-in-substrate ~/.agents/skills/
```

To update, pull and copy the folder again.

## Add a skill

Create `skills/<name>/SKILL.md`, with `name` matching the folder. To keep it portable:

- Put scripts in `scripts/` and refer to them by paths relative to `SKILL.md`, not tool-specific variables.
- Use only `name` and `description` in the frontmatter. Other fields are tool-specific.
- Keep caches and other generated data outside the skill folder, for example in `~/.cache/<skill>/`.
