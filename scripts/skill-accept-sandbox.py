#!/usr/bin/env python3
"""Run N hermes_api skill-acceptance drills on sandbox-smoke (dev-flow).

Intended to run *inside* emaw-dev-backend (or any agent with API_SERVER_KEY + :8642).
Does not print secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("HERMES_API_BASE", "http://127.0.0.1:8642").rstrip("/")
SANDBOX = Path(os.environ.get("SANDBOX_ROOT", "/workspace/sandbox-smoke"))


def _key() -> str:
    k = os.environ.get("API_SERVER_KEY", "").strip()
    if k:
        return k
    for path in (
        os.environ.get("API_SERVER_KEY_FILE", ""),
        os.environ.get("HERMES_API_KEY_FILE", ""),
        "/run/secrets/hermes_api_key",
    ):
        if path and os.path.isfile(path):
            val = open(path, encoding="utf-8").read().strip()
            if val and "=" not in val[:20]:
                return val
    env_path = "/opt/data/.env"
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("API_SERVER_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("API_SERVER_KEY not found")


def _req(method: str, path: str, body: dict | None = None, idem: str | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Authorization": "Bearer " + _key(),
        "Content-Type": "application/json",
    }
    if idem:
        headers["Idempotency-Key"] = idem[:255]
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, raw


PROMPTS = [
    (
        "dev-flow",
        "Use skill dev-flow on /workspace/sandbox-smoke. "
        "Add function subtract(a, b) returning a-b with unit test. "
        "Follow project-standards.md. Commit on a work branch (not main). "
        "Do NOT push. End with HANDOFF YAML to reviewer.",
    ),
    (
        "dev-flow",
        "Use skill dev-flow on /workspace/sandbox-smoke. "
        "If subtract already exists, add multiply(a, b) with unit test instead. "
        "Commit on a work branch. Do NOT push. End with HANDOFF YAML.",
    ),
    (
        "review-code",
        "Use skill review-code on /workspace/sandbox-smoke. "
        "Self-review the latest work-branch changes (subtract/multiply). "
        "Do not apply patches that change production code without handoff. "
        "Summarize findings and end with HANDOFF YAML.",
    ),
]


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(SANDBOX), *args],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def sandbox_commit_evidence(before_sha: str) -> tuple[bool, str]:
    """Pass only with a new non-main commit, green tests, and no upstream (no push)."""
    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        sha = _git("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return False, f"git error: {exc}"
    if branch in {"main", "master", "HEAD"}:
        return False, f"still on {branch} (need work branch)"
    if sha == before_sha:
        return False, f"no new commit (still {sha[:8]})"
    try:
        _git("rev-parse", "--abbrev-ref", "@{u}")
        return False, "upstream set — push must go through HITL"
    except subprocess.CalledProcessError:
        pass
    try:
        proc = subprocess.run(
            ["bash", str(SANDBOX / "test.sh")],
            cwd=str(SANDBOX),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"test.sh error: {exc}"
    if proc.returncode != 0:
        return False, f"test.sh exit {proc.returncode}"
    return True, f"branch={branch} sha={sha[:8]} test=green no-push"


def poll_run(run_id: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    terminal = {
        "completed",
        "failed",
        "cancelled",
        "canceled",
        "error",
        "waiting_for_approval",
        "succeeded",
        "success",
    }
    last: dict = {}
    while time.time() < deadline:
        code, payload = _req("GET", f"/v1/runs/{run_id}")
        if code != 200 or not isinstance(payload, dict):
            time.sleep(3)
            continue
        last = payload
        status = str(payload.get("status") or payload.get("state") or "").lower()
        if status in terminal:
            return last
        time.sleep(3)
    last["_poll_timeout"] = True
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=900, help="seconds per run")
    ap.add_argument("--dry-run", action="store_true", help="create runs but do not wait")
    ap.add_argument(
        "--require-commit",
        action="store_true",
        help="pass only if sandbox got a new non-main commit + green test.sh (no push)",
    )
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: list[dict] = []

    # health
    code, health = _req("GET", "/health")
    print(f"health http={code} body={health!r}"[:200])

    for i in range(args.rounds):
        skill, prompt = PROMPTS[i % len(PROMPTS)]
        idem = f"skill-accept-{stamp}-r{i+1}"
        try:
            before_sha = _git("rev-parse", "HEAD")
        except (subprocess.CalledProcessError, FileNotFoundError):
            before_sha = ""
        body = {
            "input": prompt,
            "messages": [{"role": "user", "content": prompt}],
            "metadata": {
                "task_id": idem,
                "skill": skill,
                "project": "sandbox-smoke",
                "assigned_to": "dev-backend",
            },
        }
        code, payload = _req("POST", "/v1/runs", body=body, idem=idem)
        run_id = ""
        if isinstance(payload, dict):
            run_id = str(payload.get("run_id") or payload.get("id") or "")
        print(f"round={i+1} skill={skill} create_http={code} run_id={run_id or 'n/a'}")
        row = {
            "round": i + 1,
            "skill": skill,
            "create_http": code,
            "run_id": run_id,
            "idempotency_key": idem,
            "pass": False,
            "status": "",
            "notes": "",
        }
        if code >= 300 or not run_id:
            row["notes"] = f"create failed: {payload!r}"[:300]
            results.append(row)
            continue
        if args.dry_run:
            row["notes"] = "dry-run; not polled"
            results.append(row)
            continue
        final = poll_run(run_id, args.timeout)
        status = str(final.get("status") or final.get("state") or "unknown")
        row["status"] = status
        ok_statuses = {"completed", "succeeded", "success", "waiting_for_approval"}
        status_ok = status.lower() in ok_statuses and not final.get("_poll_timeout")
        if args.require_commit:
            ev_ok, ev_note = sandbox_commit_evidence(before_sha)
            row["pass"] = bool(status_ok and ev_ok)
            row["notes"] = ev_note if not ev_ok else ev_note
            if not status_ok:
                row["notes"] = f"status={status}; {row['notes']}"
        else:
            row["pass"] = status_ok
            if final.get("_poll_timeout"):
                row["notes"] = "poll timeout"
            else:
                out = final.get("output") or final.get("result") or final.get("error") or ""
                row["notes"] = str(out)[:240]
        results.append(row)
        print(f"round={i+1} status={status} pass={row['pass']} notes={row['notes'][:120]}")

    out_path = os.environ.get(
        "SKILL_ACCEPT_OUT",
        f"/workspace/sandbox-smoke/.skill-accept-{stamp}.json",
    )
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"stamp": stamp, "results": results}, f, indent=2)
        print(f"wrote {out_path}")
    except OSError as exc:
        print(f"could not write {out_path}: {exc}", file=sys.stderr)
        print(json.dumps({"stamp": stamp, "results": results}, indent=2))

    passes = sum(1 for r in results if r["pass"])
    print(f"summary passes={passes}/{len(results)}")
    return 0 if passes >= min(3, args.rounds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
