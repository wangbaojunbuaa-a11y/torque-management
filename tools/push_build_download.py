from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


DEFAULT_EXCLUDES = ("CoatingRecordAndReport/", "dist_download/")
DEFAULT_ARTIFACTS = ("IGBT_Torque_Manager", "IGBT_Torque_Report_Center")


def run(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
    display_cmd: list[str] | None = None,
) -> str:
    print("+", " ".join(display_cmd or cmd))
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.stdout


def repo_slug() -> str:
    remote = run(["git", "remote", "get-url", "origin"]).strip()
    if remote.endswith(".git"):
        remote = remote[:-4]
    if remote.startswith("git@github.com:"):
        return remote.removeprefix("git@github.com:")
    if "github.com/" in remote:
        return remote.split("github.com/", 1)[1]
    raise SystemExit(f"Cannot parse GitHub repo from origin: {remote}")


def current_branch() -> str:
    return run(["git", "branch", "--show-current"]).strip() or "main"


def changed_paths(excludes: tuple[str, ...]) -> list[str]:
    raw = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"], text=False)
    items = raw.split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(items):
        item = items[index]
        index += 1
        if not item:
            continue
        text = item.decode("utf-8", errors="replace")
        status = text[:2]
        path = text[3:]
        if "R" in status or "C" in status:
            if index < len(items):
                new_path = items[index].decode("utf-8", errors="replace")
                index += 1
                path = new_path
        normalized = path.replace("\\", "/")
        if any(normalized == item.rstrip("/") or normalized.startswith(item) for item in excludes):
            continue
        paths.append(path)
    return sorted(set(paths))


def stage_changes(paths: list[str]) -> None:
    if not paths:
        print("No changes to stage.")
        return
    for path in paths:
        run(["git", "add", "--", path])


def commit_if_needed(message: str) -> bool:
    diff = run(["git", "diff", "--cached", "--name-only"], check=False).strip()
    if not diff:
        print("No staged changes to commit.")
        return False
    run(["git", "commit", "-m", message])
    return True


def push_with_token(branch: str) -> None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN or GH_TOKEN before pushing.")
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    run(
        [
            "git",
            "-c",
            f"http.https://github.com/.extraheader=AUTHORIZATION: basic {auth}",
            "push",
            "origin",
            branch,
        ],
        display_cmd=["git", "-c", "http.https://github.com/.extraheader=AUTHORIZATION: basic ***", "push", "origin", branch],
    )


def gh_env() -> dict[str, str]:
    env = os.environ.copy()
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if token:
        env["GH_TOKEN"] = token
    return env


def find_workflow_run(repo: str, branch: str, sha: str, workflow: str, timeout: int) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                repo,
                "--branch",
                branch,
                "--workflow",
                workflow,
                "--limit",
                "20",
                "--json",
                "databaseId,headSha,status,conclusion",
            ],
            env=gh_env(),
            check=False,
        )
        runs = json.loads(out or "[]")
        for item in runs:
            if item.get("headSha") == sha:
                return int(item["databaseId"])
        print("Waiting for GitHub Actions run to appear...")
        time.sleep(10)
    raise SystemExit("Timed out waiting for workflow run.")


def wait_for_run(repo: str, run_id: int, timeout: int) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = run(
            [
                "gh",
                "run",
                "view",
                str(run_id),
                "--repo",
                repo,
                "--json",
                "status,conclusion,url",
            ],
            env=gh_env(),
            check=False,
        )
        info = json.loads(out or "{}")
        status = info.get("status")
        conclusion = info.get("conclusion")
        print(f"Run {run_id}: status={status}, conclusion={conclusion}")
        if status == "completed":
            if conclusion != "success":
                raise SystemExit(f"Workflow failed: {info.get('url')}")
            return
        time.sleep(20)
    raise SystemExit("Timed out waiting for workflow completion.")


def backup_existing_exes(download_dir: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for exe in download_dir.glob("*.exe"):
        target = exe.with_name(f"{exe.stem}_previous_{stamp}{exe.suffix}")
        exe.rename(target)


def download_artifacts(repo: str, run_id: int, artifacts: tuple[str, ...], download_dir: Path) -> None:
    download_dir.mkdir(parents=True, exist_ok=True)
    backup_existing_exes(download_dir)
    for artifact in artifacts:
        run(
            [
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                repo,
                "--name",
                artifact,
                "--dir",
                str(download_dir),
            ],
            env=gh_env(),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Commit, push, wait for GitHub Actions, and download EXE artifacts.")
    parser.add_argument("-m", "--message", default="Add report center app")
    parser.add_argument("--workflow", default="build-windows.yml")
    parser.add_argument("--download-dir", default="dist_download")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--include-reference", action="store_true")
    args = parser.parse_args()

    excludes = () if args.include_reference else DEFAULT_EXCLUDES
    paths = changed_paths(excludes)
    stage_changes(paths)
    committed = commit_if_needed(args.message)

    branch = current_branch()
    repo = repo_slug()
    sha = run(["git", "rev-parse", "HEAD"]).strip()
    push_with_token(branch)

    if not committed:
        print("No new commit was created; waiting for the latest pushed commit.")

    run_id = find_workflow_run(repo, branch, sha, args.workflow, args.timeout)
    wait_for_run(repo, run_id, args.timeout)
    if not args.no_download:
        download_artifacts(repo, run_id, DEFAULT_ARTIFACTS, Path(args.download_dir))
    print(f"Done. Run id: {run_id}")


if __name__ == "__main__":
    if not shutil.which("gh"):
        raise SystemExit("GitHub CLI 'gh' is required.")
    main()
