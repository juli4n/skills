#!/usr/bin/env python3
"""Collect a period of activity in a GitHub repository into one JSON file.

Usage: gather.py --since YYYY-MM-DD [--until YYYY-MM-DD] [--repo OWNER/NAME] --out data.json

The window is [since, until) in UTC; until defaults to today. Requires an
authenticated `gh` and PyYAML.
"""

import argparse
import base64
import datetime as dt
import json
import re
import subprocess
import sys

import yaml

BOTS = ("dependabot", "renovate", "github-actions")
BODY_LIMIT = 1000
ISSUE_BODY_LIMIT = 400
COMMENT_LIMIT = 400


def gh_graphql(query, **variables):
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        args += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
    return json.loads(out)["data"]


def gh_rest(path):
    out = subprocess.run(["gh", "api", "--paginate", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def search(query, fragment, limit=1000):
    q = """query($q: String!, $after: String) {
      search(query: $q, type: ISSUE, first: 50, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { %s }
      }
    }""" % fragment
    nodes, after = [], None
    while len(nodes) < limit:
        vars = {"q": query}
        if after:
            vars["after"] = after
        page = gh_graphql(q, **vars)["search"]
        nodes += [n for n in page["nodes"] if n]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return nodes[:limit]


def trunc(s, n):
    s = (s or "").strip()
    if n == 0:
        return ""
    return s if len(s) <= n else s[:n] + " …[truncated]"


def strip_template(body):
    # Drop the PR template's checklist and HTML comments; they carry no content.
    out, in_comment = [], False
    for line in (body or "").splitlines():
        if "<!--" in line:
            in_comment = "-->" not in line
            continue
        if in_comment:
            in_comment = "-->" not in line
            continue
        if line.strip().startswith(("- [ ]", "- [x]", "> It's a good idea", "Fixes #<issue")):
            continue
        out.append(line)
    return "\n".join(out).strip()


def breaking_note(body):
    """Return the text of the PR template's "Breaking change" section, if filled in."""
    out, inside = [], False
    for line in strip_template((body or "").replace("\r", "")).splitlines():
        if re.match(r"#+\s*breaking changes?\s*$", line.strip(), re.I):
            inside = True
            continue
        if inside and (line.startswith("#") or line.strip() == "----"):
            break
        if inside:
            out.append(line)
    note = "\n".join(out).strip()
    return "" if re.match(r"(none|n/?a|no)\b", note, re.I) else note


def is_bot(login):
    return login is None or login.endswith("[bot]") or login in BOTS


def in_window(ts, since, until):
    return ts is not None and since <= ts < until


def load_categories(repo):
    try:
        f = gh_graphql(
            """query($o: String!, $n: String!) { repository(owner: $o, name: $n) {
              object(expression: "HEAD:.github/release.yml") { ... on Blob { text } } } }""",
            o=repo.split("/")[0], n=repo.split("/")[1])
        text = f["repository"]["object"]["text"]
    except Exception:
        return None, None
    cfg = yaml.safe_load(text)["changelog"]
    return cfg.get("exclude", {}).get("labels", []), cfg["categories"]


def categorize(labels, categories):
    """Mirror GitHub's release-note rule: first category whose labels match wins."""
    for c in categories:
        excl = set(c.get("exclude", {}).get("labels", []))
        if excl & labels:
            continue
        want = c.get("labels", [])
        if "*" in want or set(want) & labels:
            return c["title"]
    return "Other Changes"


PR_FIELDS = """... on PullRequest {
  number title url body mergedAt additions deletions changedFiles
  author { login } labels(first: 20) { nodes { name } }
  comments { totalCount } reviews { totalCount }
  closingIssuesReferences(first: 5) { nodes { number title } }
  files(first: 100) { nodes { path changeType } }
}"""

ISSUE_FIELDS = """... on Issue {
  number title url body createdAt closedAt state stateReason
  author { login } labels(first: 20) { nodes { name } }
  comments { totalCount } reactions { totalCount }
}"""

THREAD_FIELDS = """... on Issue {
  __typename number title url body state createdAt author { login }
  labels(first: 20) { nodes { name } } reactions { totalCount }
  comments(last: 40) { totalCount nodes { createdAt body author { login } } }
}
... on PullRequest {
  __typename number title url body state createdAt mergedAt author { login }
  labels(first: 20) { nodes { name } } reactions { totalCount }
  comments(last: 40) { totalCount nodes { createdAt body author { login } } }
  reviews(last: 40) { totalCount nodes { createdAt body author { login } } }
}"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default="agent-substrate/substrate")
    p.add_argument("--since", required=True)
    p.add_argument("--until", default=dt.date.today().isoformat())
    p.add_argument("--out", required=True)
    a = p.parse_args()

    since, until = a.since + "T00:00:00Z", a.until + "T00:00:00Z"
    last_day = (dt.date.fromisoformat(a.until) - dt.timedelta(days=1)).isoformat()
    rng = f"{a.since}..{last_day}"
    repo = a.repo
    excluded, categories = load_categories(repo)
    if categories is None:
        print("warning: could not read .github/release.yml; all PRs land in Other Changes", file=sys.stderr)
        excluded, categories = [], []

    # Merged PRs.
    prs = []
    for n in search(f"repo:{repo} is:pr is:merged merged:{rng}", PR_FIELDS):
        if not in_window(n["mergedAt"], since, until):
            continue
        login = (n["author"] or {}).get("login")
        labels = {l["name"] for l in n["labels"]["nodes"]}
        files = [f["path"] for f in n["files"]["nodes"]]
        prs.append({
            "number": n["number"],
            "title": n["title"],
            "url": n["url"],
            "author": login,
            "bot": is_bot(login),
            "merged_at": n["mergedAt"],
            "labels": sorted(labels),
            "section": categorize(labels, categories),
            "excluded_from_notes": bool(labels & set(excluded)),
            "breaking_note": trunc(breaking_note(n["body"]), BODY_LIMIT),
            "size": {"additions": n["additions"], "deletions": n["deletions"], "files": n["changedFiles"]},
            "activity": {"comments": n["comments"]["totalCount"], "reviews": n["reviews"]["totalCount"]},
            "closes": [{"number": i["number"], "title": i["title"]} for i in n["closingIssuesReferences"]["nodes"]],
            "top_dirs": sorted({"/".join(f.split("/")[:2]) for f in files}),
            "docs_files": [f"{x['changeType']} {x['path']}" for x in n["files"]["nodes"]
                           if x["path"].startswith("docs/") or x["path"].endswith(".md")],
            "body": trunc(strip_template(n["body"]), BODY_LIMIT),
        })
    prs.sort(key=lambda x: x["merged_at"])

    def issue(n, body_limit):
        return {
            "number": n["number"], "title": n["title"], "url": n["url"],
            "author": (n["author"] or {}).get("login"), "state": n["state"],
            "state_reason": n.get("stateReason"), "created_at": n["createdAt"], "closed_at": n.get("closedAt"),
            "labels": sorted(l["name"] for l in n["labels"]["nodes"]),
            "comments": n["comments"]["totalCount"], "reactions": n["reactions"]["totalCount"],
            "body": trunc(n["body"], body_limit),
        }

    opened = [issue(n, ISSUE_BODY_LIMIT) for n in search(f"repo:{repo} is:issue created:{rng}", ISSUE_FIELDS)
              if in_window(n["createdAt"], since, until)]
    closed = [issue(n, 0) for n in search(f"repo:{repo} is:issue closed:{rng}", ISSUE_FIELDS)
              if in_window(n["closedAt"], since, until)]

    # Discussion threads: most-commented issues and PRs updated in the window,
    # ranked by comments and reviews made inside the window.
    threads = []
    for n in search(f"repo:{repo} updated:{rng} sort:comments-desc", THREAD_FIELDS, limit=100):
        events = [c for c in n["comments"]["nodes"] if in_window(c["createdAt"], since, until)]
        events += [r for r in (n.get("reviews") or {}).get("nodes", [])
                   if in_window(r["createdAt"], since, until) and r["body"].strip()]
        humans = {(e["author"] or {}).get("login") for e in events} - {None}
        humans = {h for h in humans if not is_bot(h)}
        if len(events) < 3:
            continue
        events.sort(key=lambda e: e["createdAt"])
        threads.append({
            "kind": "pr" if n["__typename"] == "PullRequest" else "issue",
            "number": n["number"], "title": n["title"], "url": n["url"], "state": n["state"],
            "author": (n["author"] or {}).get("login"),
            "labels": sorted(l["name"] for l in n["labels"]["nodes"]),
            "comments_in_window": len(events), "participants": sorted(humans),
            "reactions": n["reactions"]["totalCount"],
            "body": trunc(strip_template(n["body"]), 800),
            "recent_comments": [{"author": (e["author"] or {}).get("login"), "at": e["createdAt"],
                                 "body": trunc(e["body"], COMMENT_LIMIT)} for e in events[-8:]],
        })
    threads.sort(key=lambda t: -t["comments_in_window"])
    threads = threads[:25]

    releases = [{"tag": r["tag_name"], "name": r["name"], "url": r["html_url"],
                 "published_at": r["published_at"], "prerelease": r["prerelease"]}
                for r in gh_rest(f"repos/{repo}/releases?per_page=30")
                if not r["draft"] and in_window(r["published_at"], since, until)]
    # For each release, which of the window's PRs landed after it (and so ship in a later release).
    window_prs = {p["number"] for p in prs}
    for r in releases:
        cmp = gh_rest(f"repos/{repo}/compare/{r['tag']}...HEAD?per_page=250")
        after = set()
        for c in cmp.get("commits", []):
            m = re.search(r"\(#(\d+)\)\s*$", c["commit"]["message"].splitlines()[0])
            if m:
                after.add(int(m.group(1)))
        r["window_prs_after_release"] = sorted(after & window_prs)
        r["window_prs_in_release"] = sorted(window_prs - after)

    # Contributors and first-time contributors (no merged PR before the window).
    authors = sorted({pr["author"] for pr in prs if not pr["bot"]})
    first_timers = []
    if authors:
        q = "{" + " ".join(
            f'a{i}: search(query: "repo:{repo} is:pr is:merged author:{login} merged:<{a.since}", type: ISSUE) {{ issueCount }}'
            for i, login in enumerate(authors)) + "}"
        counts = gh_graphql(q)
        first_timers = [login for i, login in enumerate(authors) if counts[f"a{i}"]["issueCount"] == 0]

    data = {
        "repo": repo,
        "since": a.since,
        "until": a.until,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "section_order": [c["title"] for c in categories] or ["Other Changes"],
        "stats": {
            "prs_merged": len([p for p in prs if not p["bot"]]),
            "bot_prs_merged": len([p for p in prs if p["bot"]]),
            "contributors": len(authors),
            "issues_opened": len(opened),
            "issues_closed": len(closed),
        },
        "contributors": authors,
        "first_time_contributors": first_timers,
        "releases": releases,
        "prs": prs,
        "issues_opened": opened,
        "issues_closed": closed,
        "threads": threads,
    }
    with open(a.out, "w") as f:
        json.dump(data, f, indent=1)
    s = data["stats"]
    print(f"{a.out}: {s['prs_merged']} PRs (+{s['bot_prs_merged']} bot), {s['contributors']} contributors, "
          f"{s['issues_opened']} issues opened, {s['issues_closed']} closed, {len(threads)} threads, "
          f"{len(releases)} releases, {len(first_timers)} first-time contributors")


if __name__ == "__main__":
    main()
