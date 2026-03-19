import argparse
import os
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Normalize GitHub/GitLab CI event payload and call pr_event_sync.py")
    p.add_argument("--source", choices=["auto", "github", "gitlab"], default="auto")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def detect_source(preferred: str) -> str:
    if preferred != "auto":
        return preferred
    if os.getenv("GITHUB_ACTIONS") == "true":
        return "github"
    if os.getenv("GITLAB_CI") == "true":
        return "gitlab"
    raise SystemExit("Unable to detect CI source. Use --source github|gitlab")


def github_event() -> tuple[str, str, str, str]:
    action = (os.getenv("GITHUB_EVENT_ACTION") or "").strip().lower()
    merged = (os.getenv("GITHUB_PR_MERGED") or "").strip().lower() == "true"
    title = (os.getenv("GITHUB_PR_TITLE") or "").strip()
    url = (os.getenv("GITHUB_PR_URL") or "").strip()
    body = (os.getenv("GITHUB_PR_BODY") or "").strip()

    if not title:
        raise SystemExit("Missing GITHUB_PR_TITLE")
    if action == "closed" and merged:
        return "merged", title, url, body
    if action in {"opened", "closed", "edited", "synchronize", "reopened"}:
        event = "updated" if action in {"edited", "synchronize", "reopened"} else action
        return event, title, url, body
    return "updated", title, url, body


def gitlab_event() -> tuple[str, str, str, str]:
    state = (os.getenv("CI_MERGE_REQUEST_STATE") or "").strip().lower()
    title = (os.getenv("CI_MERGE_REQUEST_TITLE") or "").strip()
    url = (os.getenv("CI_MERGE_REQUEST_PROJECT_URL") or "").strip()
    iid = (os.getenv("CI_MERGE_REQUEST_IID") or "").strip()
    body = (os.getenv("CI_MERGE_REQUEST_DESCRIPTION") or "").strip()
    if url and iid:
        url = f"{url}/-/merge_requests/{iid}"

    if not title:
        raise SystemExit("Missing CI_MERGE_REQUEST_TITLE")
    event = "merged" if state == "merged" else "updated"
    return event, title, url, body


def main() -> None:
    args = parse_args()
    source = detect_source(args.source)
    if source == "github":
        event, title, url, body = github_event()
    else:
        event, title, url, body = gitlab_event()

    script = os.path.join(os.path.dirname(__file__), "pr_event_sync.py")
    cmd = [sys.executable, script, "--event", event, "--title", title]
    if url:
        cmd.extend(["--url", url])
    if body:
        cmd.extend(["--body", body])
    if args.dry_run:
        cmd.append("--dry-run")

    subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
