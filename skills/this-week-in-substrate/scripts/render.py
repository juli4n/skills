#!/usr/bin/env python3
"""Render a weekly report as one self-contained HTML page.

Usage: render.py --data data.json --report report.json --out index.html

data.json comes from gather.py. report.json holds the editorial content:

{
  "title": "This Week in Agent Substrate",
  "tldr": "One paragraph.",
  "highlights": [{"heading": "...", "body": "...", "refs": [123]}],
  "breaking": [{"text": "...", "refs": [123]}],
  "sections": [{"heading": "...", "items": [{"text": "...", "refs": [123]}]}],
  "discussions": [{"heading": "...", "body": "...", "refs": [123]}],
  "closing": "Optional closing paragraph."
}

Text fields accept a small Markdown subset: blank-line paragraphs, "- " bullet
lines, `code`, **bold**, [text](https://url) and #123 references. Every
reference must exist in data.json, and every breaking-change PR must be cited
under "breaking"; otherwise the script prints the problems and exits 1.
"""

import argparse
import datetime as dt
import html
import json
import re
import sys

REF = re.compile(r"(?<![\w&/])#(\d+)\b")


class Refs:
    def __init__(self, data):
        self.items = {}
        for t in data["threads"]:
            self.items[t["number"]] = (t["title"], t["url"])
        for i in data["issues_opened"] + data["issues_closed"]:
            self.items[i["number"]] = (i["title"], i["url"])
        for p in data["prs"]:
            self.items[p["number"]] = (p["title"], p["url"])
        self.repo = data["repo"]
        self.unknown = set()
        self.cited = set()

    def link(self, n, label=None):
        n = int(n)
        self.cited.add(n)
        if n not in self.items:
            self.unknown.add(n)
            url, title = f"https://github.com/{self.repo}/issues/{n}", ""
        else:
            title, url = self.items[n]
        return (f'<a class="ref" href="{html.escape(url)}" title="{html.escape(title)}">'
                f'{html.escape(label or f"#{n}")}</a>')


def inline(text, refs):
    out, pos = [], 0
    # Split out code spans first so nothing inside them is rewritten.
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(_inline_plain(text[pos:m.start()], refs))
        out.append(f"<code>{html.escape(m.group(1))}</code>")
        pos = m.end()
    out.append(_inline_plain(text[pos:], refs))
    return "".join(out)


def _inline_plain(text, refs):
    links = []

    def stash(m):
        links.append(f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>')
        return f"\x00{len(links) - 1}\x00"

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", stash, text)
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = REF.sub(lambda m: refs.link(m.group(1)), s)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], s)


def block(text, refs):
    parts = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l for l in para.splitlines() if l.strip()]
        if lines and all(l.lstrip().startswith("- ") for l in lines):
            items = "".join(f"<li>{inline(l.lstrip()[2:], refs)}</li>" for l in lines)
            parts.append(f"<ul>{items}</ul>")
        elif lines:
            parts.append(f"<p>{inline(' '.join(l.strip() for l in lines), refs)}</p>")
    return "".join(parts)


def chips(ns, refs, *texts):
    # Only list the references the text does not already link inline.
    inline_refs = {int(n) for t in texts for n in REF.findall(t or "")}
    ns = [n for n in (ns or []) if n not in inline_refs]
    if not ns:
        return ""
    return '<span class="chips">' + "".join(refs.link(n) for n in ns) + "</span>"


def fmt_range(since, until):
    a = dt.date.fromisoformat(since)
    b = dt.date.fromisoformat(until) - dt.timedelta(days=1)
    if a.year != b.year:
        return f"{a:%B} {a.day}, {a.year} – {b:%B} {b.day}, {b.year}"
    if a.month != b.month:
        return f"{a:%B} {a.day} – {b:%B} {b.day}, {b.year}"
    return f"{a:%B} {a.day}–{b.day}, {b.year}"


CSS = """
:root{--bg:#fbfaf8;--surface:#fff;--text:#1d1d1f;--muted:#5f6368;--border:#e4e2dd;
--accent:#3456c8;--accent-soft:#eef1fb;--warn:#a5480b;--warn-soft:#fdf2e8;--code:#f2f1ee;--good:#1e7a46}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141416;--surface:#1c1c1f;
--text:#e8e8ea;--muted:#a0a0a8;--border:#2e2e33;--accent:#8ea6ff;--accent-soft:#1f2540;
--warn:#f0a565;--warn-soft:#33241a;--code:#26262b;--good:#5fd08e}}
:root[data-theme="dark"]{--bg:#141416;--surface:#1c1c1f;--text:#e8e8ea;--muted:#a0a0a8;--border:#2e2e33;
--accent:#8ea6ff;--accent-soft:#1f2540;--warn:#f0a565;--warn-soft:#33241a;--code:#26262b;--good:#5fd08e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:760px;margin:0 auto;padding:48px 16px 64px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
code{font:0.88em ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--code);padding:1px 5px;border-radius:4px;overflow-wrap:anywhere}
header .eyebrow{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font-size:clamp(30px,6vw,42px);line-height:1.15;margin:6px 0 4px;letter-spacing:-.02em}
header .range{color:var(--muted);margin:0}
.stats{display:flex;flex-wrap:wrap;gap:1px;background:var(--border);
border:1px solid var(--border);border-radius:12px;overflow:hidden;margin:28px 0}
.stat{flex:1 1 120px;background:var(--surface);padding:14px 16px}
.stat b{display:block;font-size:26px;line-height:1.2;font-variant-numeric:tabular-nums}
.stat span{font-size:13px;color:var(--muted)}
.tldr{font-size:18px;line-height:1.55;border-left:3px solid var(--accent);padding:2px 0 2px 18px;margin:0 0 8px}
.tldr p{margin:0 0 .6em}
.release{display:flex;gap:10px;align-items:baseline;background:var(--accent-soft);border-radius:10px;padding:12px 16px;margin:20px 0}
.release .tag{font-weight:700}
h2{font-size:22px;margin:48px 0 14px;letter-spacing:-.01em}
h2 .count{font-size:14px;font-weight:500;color:var(--muted);margin-left:6px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin:0 0 14px}
.card h3{font-size:18px;margin:0 0 6px}
.card p{margin:0 0 .7em}.card p:last-of-type{margin-bottom:.4em}
.card ul{margin:.2em 0 .7em;padding-left:1.2em}
.chips{display:inline-flex;flex-wrap:wrap;gap:6px;margin-left:4px;vertical-align:baseline}
.card>.chips{margin:4px 0 0}
.chips .ref{font-size:12.5px;font-variant-numeric:tabular-nums;background:var(--accent-soft);padding:1px 8px;border-radius:999px}
.breaking{background:var(--warn-soft);border-radius:12px;padding:6px 20px}
.breaking h2{color:var(--warn);margin-top:20px}
ul.items{padding-left:1.2em;margin:0}
ul.items li{margin:0 0 8px}
h3.section{font-size:15px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:28px 0 10px}
.people{display:flex;flex-wrap:wrap;gap:8px;padding:0;margin:0;list-style:none}
.people a{display:inline-block;border:1px solid var(--border);background:var(--surface);border-radius:999px;padding:3px 12px;font-size:14px}
.people.new a{border-color:var(--good);color:var(--good)}
details{border:1px solid var(--border);border-radius:10px;background:var(--surface);margin:0 0 8px}
summary{cursor:pointer;padding:10px 16px;font-weight:600}
summary .count{color:var(--muted);font-weight:500}
details ul{margin:0;padding:0 16px 12px 34px;font-size:14.5px}
details li{margin:0 0 4px}
details .by{color:var(--muted)}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:13px}
@media (max-width:520px){main{padding-top:28px}.tldr{font-size:17px}.card{padding:16px}}
"""


def render(data, report):
    refs = Refs(data)
    s = data["stats"]
    repo = data["repo"]
    gh = f"https://github.com/{repo}"
    last_day = (dt.date.fromisoformat(data["until"]) - dt.timedelta(days=1)).isoformat()
    rng = f"{data['since']}..{last_day}"
    title = report.get("title", "This Week in Agent Substrate")
    out = []
    w = out.append

    w(f'<header><div class="eyebrow">Agent Substrate · Weekly</div><h1>{html.escape(title)}</h1>'
      f'<p class="range">{fmt_range(data["since"], data["until"])}</p></header>')

    stats = [
        (s["prs_merged"], "pull requests merged", f"{gh}/pulls?q=is%3Apr+is%3Amerged+merged%3A{rng}"),
        (s["contributors"], "contributors", None),
        (len(data["first_time_contributors"]), "first-time contributors", None),
        (s["issues_opened"], "issues opened", f"{gh}/issues?q=is%3Aissue+created%3A{rng}"),
        (s["issues_closed"], "issues closed", f"{gh}/issues?q=is%3Aissue+closed%3A{rng}"),
    ]
    def stat(n, label, url):
        num = f'<a href="{html.escape(url)}">{n}</a>' if url else str(n)
        return f'<div class="stat"><b>{num}</b><span>{label}</span></div>'

    w('<div class="stats">' + "".join(stat(*x) for x in stats) + "</div>")

    if report.get("tldr"):
        w(f'<div class="tldr">{block(report["tldr"], refs)}</div>')

    for r in data["releases"]:
        kind = "pre-release" if r["prerelease"] else "release"
        w(f'<div class="release"><span>📦 New {kind}</span><a class="tag" href="{html.escape(r["url"])}">'
          f'{html.escape(r["name"] or r["tag"])}</a></div>')

    if report.get("highlights"):
        w("<h2>Highlights</h2>")
        for h in report["highlights"]:
            w(f'<article class="card"><h3>{inline(h["heading"], refs)}</h3>{block(h.get("body"), refs)}'
              f'{chips(h.get("refs"), refs, h["heading"], h.get("body"))}</article>')

    if report.get("breaking"):
        w('<section class="breaking"><h2>⚠️ Breaking changes</h2><ul class="items">')
        for b in report["breaking"]:
            w(f'<li>{inline(b["text"], refs)} {chips(b.get("refs"), refs, b["text"])}</li>')
        w("</ul></section>")

    if report.get("sections"):
        w("<h2>What else changed</h2>")
        for sec in report["sections"]:
            w(f'<h3 class="section">{html.escape(sec["heading"])}</h3><ul class="items">')
            for it in sec["items"]:
                w(f'<li>{inline(it["text"], refs)} {chips(it.get("refs"), refs, it["text"])}</li>')
            w("</ul>")

    if report.get("discussions"):
        w("<h2>Discussions worth following</h2>")
        for d in report["discussions"]:
            w(f'<article class="card"><h3>{inline(d["heading"], refs)}</h3>{block(d.get("body"), refs)}'
              f'{chips(d.get("refs"), refs, d["heading"], d.get("body"))}</article>')

    if data["first_time_contributors"]:
        w(f'<h2>Welcome, new contributors<span class="count">{len(data["first_time_contributors"])}</span></h2>'
          '<ul class="people new">' + "".join(
              f'<li><a href="https://github.com/{html.escape(u)}">@{html.escape(u)}</a></li>'
              for u in data["first_time_contributors"]) + "</ul>")
    w(f'<h2>Thank you<span class="count">{len(data["contributors"])} contributors</span></h2><ul class="people">' +
      "".join(f'<li><a href="https://github.com/{html.escape(u)}">@{html.escape(u)}</a></li>'
              for u in data["contributors"]) + "</ul>")

    if report.get("closing"):
        w(f'<div style="margin-top:32px">{block(report["closing"], refs)}</div>')

    # Every merged PR, grouped the way the release notes are.
    by_section = {}
    for p in data["prs"]:
        if not p["excluded_from_notes"]:
            by_section.setdefault(p["section"], []).append(p)
    w(f'<h2>All merged pull requests<span class="count">{sum(map(len, by_section.values()))}</span></h2>')
    for name in data["section_order"] + sorted(set(by_section) - set(data["section_order"])):
        prs = by_section.get(name)
        if not prs:
            continue
        lis = "".join(
            f'<li><a href="{html.escape(p["url"])}">{html.escape(p["title"])}</a> '
            f'<span class="by">#{p["number"]} by @{html.escape(p["author"] or "ghost")}</span></li>'
            for p in sorted(prs, key=lambda p: p["number"]))
        w(f'<details><summary>{html.escape(name)} <span class="count">({len(prs)})</span></summary><ul>{lis}</ul></details>')

    w(f'<footer>Covers <a href="{gh}">{html.escape(repo)}</a> activity from {data["since"]} up to {data["until"]} (UTC). '
      f'Generated {data["generated_at"]}.</footer>')

    body = "\n".join(out)
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)} · {fmt_range(data["since"], data["until"])}</title>'
            f'<style>{CSS}</style></head><body><main>{body}</main></body></html>\n')
    return page, refs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    data = json.load(open(a.data))
    report = json.load(open(a.report))
    page, refs = render(data, report)

    errors = []
    if refs.unknown:
        errors.append("references not found in data.json: " + ", ".join(f"#{n}" for n in sorted(refs.unknown)))
    breaking_cited = set()
    for b in report.get("breaking", []):
        breaking_cited |= set(b.get("refs", [])) | {int(n) for n in REF.findall(b["text"])}
    missing = [p["number"] for p in data["prs"]
               if "breaking-change" in p["labels"] and not p["excluded_from_notes"]
               and p["number"] not in breaking_cited]
    if missing:
        errors.append("breaking-change PRs not cited under \"breaking\": " + ", ".join(f"#{n}" for n in missing))
    unlabeled = [p["number"] for p in data["prs"]
                 if p.get("breaking_note") and "breaking-change" not in p["labels"]
                 and p["number"] not in breaking_cited]
    if unlabeled:
        print("warning: PRs with a \"Breaking change\" section but no breaking-change label, not cited under "
              "\"breaking\": " + ", ".join(f"#{n}" for n in unlabeled) + ". Confirm each is not breaking.",
              file=sys.stderr)
    if errors:
        for e in errors:
            print("error:", e, file=sys.stderr)
        sys.exit(1)

    with open(a.out, "w") as f:
        f.write(page)
    print(f"{a.out}: {len(page)} bytes, {len(refs.cited)} distinct references")


if __name__ == "__main__":
    main()
