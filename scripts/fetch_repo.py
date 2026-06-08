#!/usr/bin/env python3
"""Stage 1: shallow-clone a public GitHub repo and capture meta."""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

MAX_SIZE_MB = 500
GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?/?$"
)


def parse_url(url: str):
    m = GITHUB_URL_RE.match(url.strip())
    if not m:
        sys.exit(f"ERROR: not a github.com URL: {url}")
    owner, repo, branch = m.group(1), m.group(2), m.group(3)
    return owner, repo, branch


def fetch_meta(owner: str, repo: str) -> dict:
    api = f"https://api.github.com/repos/{owner}/{repo}"
    req = urllib.request.Request(api, headers={"User-Agent": "repo-explainer"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return {
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "stars": data.get("stargazers_count"),
            "language": data.get("language"),
            "default_branch": data.get("default_branch"),
            "size_kb": data.get("size"),
            "topics": data.get("topics", []),
            "html_url": data.get("html_url"),
        }
    except Exception as e:
        return {"error": str(e), "full_name": f"{owner}/{repo}"}


def clone(owner: str, repo: str, branch: str | None, workdir: Path) -> Path:
    target = workdir / f"{owner}__{repo}"
    if target.exists():
        subprocess.run(["rm", "-rf", str(target)], check=True)
    cmd = ["git", "clone", "--depth=1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [f"https://github.com/{owner}/{repo}.git", str(target)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: git clone failed: {r.stderr}")
    # size check
    du = subprocess.run(["du", "-sm", str(target)], capture_output=True, text=True)
    size_mb = int(du.stdout.split()[0])
    if size_mb > MAX_SIZE_MB:
        sys.exit(
            f"ERROR: repo size {size_mb}MB exceeds limit {MAX_SIZE_MB}MB. "
            "Re-run with --subpath to focus on a sub-directory."
        )
    # capture commit SHA
    sha = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip()
    return target, sha, size_mb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--subpath", default=None)
    ap.add_argument("--workdir", default="./workspace")
    args = ap.parse_args()

    owner, repo, branch = parse_url(args.url)
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    meta = fetch_meta(owner, repo)
    target, sha, size_mb = clone(owner, repo, branch, workdir)

    out = {
        "owner": owner,
        "repo": repo,
        "branch": branch or meta.get("default_branch"),
        "commit_sha": sha,
        "local_path": str(target),
        "subpath": args.subpath,
        "size_mb": size_mb,
        "github_meta": meta,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
