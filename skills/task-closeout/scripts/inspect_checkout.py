#!/usr/bin/env python3
"""Bounded, read-only Git inventory. No contents, mutations, or network calls."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def git(repo, *args, optional=False):
    result = subprocess.run(
        ["git", "--no-optional-locks", "--literal-pathspecs", "-C", str(repo), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
    )
    if result.returncode:
        if optional:
            return None
        raise RuntimeError(f"Git {args[0]} failed (exit {result.returncode})")
    return result.stdout


def decode(value):
    return value.decode("utf-8", "surrogateescape")


def status_paths(raw):
    records = iter(raw.split(b"\0"))
    changes = []
    for record in records:
        if not record:
            continue
        status_code, path = decode(record[:2]), decode(record[3:])
        item = {"path": path, "status": status_code}
        if "R" in status_code or "C" in status_code:
            item["previous_path"] = decode(next(records))
        changes.append(item)
    return changes


def tree_entries(raw):
    entries = {}
    for row in raw.split(b"\0"):
        if row:
            header, path = row.split(b"\t", 1)
            mode, kind, oid = decode(header).split()
            entries[decode(path)] = (mode, kind, oid)
    return entries


def index_entries(raw):
    entries = {}
    for row in raw.split(b"\0"):
        if row:
            header, path = row.split(b"\t", 1)
            mode, oid, stage = decode(header).split()
            if stage == "0":
                entries[decode(path)] = (mode, "blob", oid)
    return entries


def protected(path):
    name = path.name.lower()
    return (
        name == ".env" or name.startswith(".env.")
        or name in {".npmrc", ".netrc", ".pypirc", "cookies.json", "storagestate.json", "storage-state.json"}
        or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".har"}
        or "credentials" in {part.lower() for part in path.parts}
    )


def compare(repo, item, base_entries, index, object_format, max_bytes):
    path = repo / item["path"]
    code = item["status"]
    if "U" in code or code in {"AA", "DD"}:
        return {**item, "comparison": "conflict"}
    if "previous_path" in item:
        return {**item, "comparison": "rename_or_copy_needs_review"}
    if protected(Path(item["path"])):
        return {**item, "comparison": "protected_not_read"}
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        working = None
    else:
        if stat.S_ISLNK(metadata.st_mode):
            data = os.fsencode(os.readlink(path))
            mode = "120000"
        elif stat.S_ISREG(metadata.st_mode):
            if metadata.st_size > max_bytes:
                return {**item, "comparison": "large_file_not_read", "bytes": metadata.st_size}
            with path.open("rb") as stream:
                data = stream.read(max_bytes + 1)
            if len(data) > max_bytes:
                return {**item, "comparison": "large_file_not_read"}
            mode = "100755" if metadata.st_mode & 0o111 else "100644"
        else:
            return {**item, "comparison": "directory_or_special_file"}
        digest = hashlib.new(object_format, b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        working = (mode, "blob", digest)
    base = base_entries.get(item["path"])
    working_matches = working == base
    staged = code[0] not in {" ", "?"}
    staged_matches = index.get(item["path"]) == base if staged else None
    comparison = "matches_base" if working_matches else "differs_from_base"
    if staged and not staged_matches:
        comparison = "staged_residue"
    return {**item, "comparison": comparison, "working_matches_base": working_matches,
            "staged_matches_base": staged_matches}


def worktrees(repo):
    rows, current = [], {}
    for field in git(repo, "worktree", "list", "--porcelain", "-z").split(b"\0"):
        if not field:
            if current:
                rows.append(current)
                current = {}
            continue
        key, _, value = decode(field).partition(" ")
        if key in {"worktree", "HEAD", "branch", "locked", "prunable", "detached"}:
            current[key] = value or True
    if current:
        rows.append(current)
    return rows


def inspect_checkout(directory, base_ref=None, limit=80, max_bytes=1048576):
    repo = Path(decode(git(directory, "rev-parse", "--show-toplevel")).rstrip("\n"))
    head = git(repo, "rev-parse", "--verify", "HEAD", optional=True)
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", optional=True)
    candidates = [base_ref] if base_ref else []
    if not base_ref:
        default = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", optional=True)
        candidates = ([decode(default).strip()] if default else []) + ["origin/main", "origin/master"]
    base_sha, selected = None, None
    for candidate in candidates:
        value = git(repo, "rev-parse", "--verify", f"{candidate}^{{commit}}", optional=True)
        if value:
            selected, base_sha = candidate, decode(value).strip()
            break
    changes = status_paths(git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
    sampled = changes[:limit]
    compared = sampled
    if sampled and base_sha:
        paths = [item["path"] for item in sampled]
        base_entries = tree_entries(git(repo, "ls-tree", "-rz", base_sha, "--", *paths))
        index = index_entries(git(repo, "ls-files", "--stage", "-z", "--", *paths))
        object_format = decode(git(repo, "rev-parse", "--show-object-format")).strip()
        compared = [compare(repo, item, base_entries, index, object_format, max_bytes) for item in sampled]
    else:
        compared = [{**item, "comparison": "base_unavailable"} for item in sampled]
    return {
        "repo": str(repo), "head": decode(head).strip() if head else None,
        "branch": decode(branch).strip() if branch else None,
        "base_ref": selected, "base_sha": base_sha, "base_source": "local_ref_only",
        "dirty_paths": len(changes), "inspected_paths": len(compared),
        "omitted_paths": len(changes) - len(compared),
        "comparisons": dict(Counter(item["comparison"] for item in compared)),
        "changes": compared, "worktrees": worktrees(repo),
        "ownership_and_live_activity": "not_checked", "read_only": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repos", nargs="*", default=["."])
    parser.add_argument("--base-ref")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--max-bytes", type=int, default=1048576)
    args = parser.parse_args()
    if args.limit < 1 or args.max_bytes < 1:
        parser.error("--limit and --max-bytes must be positive")
    reports, failed = [], False
    for directory in args.repos:
        try:
            reports.append(inspect_checkout(directory, args.base_ref, args.limit, args.max_bytes))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            failed = True
            reports.append({"repo": str(directory), "error": type(error).__name__, "read_only": True})
    print(json.dumps(reports, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
