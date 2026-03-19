import argparse
import base64
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

import requests


def jira_headers(base_url: str, email: str, token: str) -> Dict[str, str]:
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def get_transition_id(base_url: str, issue_key: str, headers: Dict[str, str], keywords: list) -> Optional[str]:
    r = requests.get(f"{base_url}/rest/api/3/issue/{issue_key}/transitions", headers=headers, timeout=20)
    r.raise_for_status()
    for t in r.json().get("transitions", []):
        name = (t.get("name") or "").lower()
        if any(k in name for k in keywords):
            return t.get("id")
    return None


def transition_status(base_url: str, issue_key: str, headers: Dict[str, str], keywords: list) -> bool:
    tid = get_transition_id(base_url, issue_key, headers, keywords)
    if not tid:
        return False
    resp = requests.post(
        f"{base_url}/rest/api/3/issue/{issue_key}/transitions",
        headers=headers,
        data=json.dumps({"transition": {"id": tid}}),
        timeout=20,
    )
    resp.raise_for_status()
    return True


def transition_done(base_url: str, issue_key: str, headers: Dict[str, str]) -> bool:
    return transition_status(base_url, issue_key, headers, ["done", "완료", "해결", "closed", "종료"])


def transition_in_review(base_url: str, issue_key: str, headers: Dict[str, str]) -> bool:
    return transition_status(base_url, issue_key, headers, ["review", "검토", "리뷰", "in review"])


def add_jira_comment(base_url: str, issue_key: str, headers: Dict[str, str], text: str) -> None:
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }
    }
    r = requests.post(f"{base_url}/rest/api/3/issue/{issue_key}/comment", headers=headers, data=json.dumps(payload), timeout=20)
    r.raise_for_status()


def upsert_notion_log(notion_token: str, database_id: str, issue_key: str, event: str, summary: str) -> None:
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {"title": [{"text": {"content": f"{issue_key} {event}"}}]},
            "IssueKey": {"rich_text": [{"text": {"content": issue_key}}]},
            "Event": {"rich_text": [{"text": {"content": event}}]},
            "Summary": {"rich_text": [{"text": {"content": summary[:1800]}}]},
        },
    }
    r = requests.post("https://api.notion.com/v1/pages", headers=headers, data=json.dumps(payload), timeout=20)
    r.raise_for_status()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync PR event to Jira/Notion")
    p.add_argument("--event", required=True, choices=["opened", "merged", "closed", "updated"])
    p.add_argument("--title", required=True)
    p.add_argument("--url", default="")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_wrapping_quotes(v.strip())


def preload_env() -> None:
    cwd = Path.cwd()
    candidates = [
        cwd / ".env",
        cwd / ".env.jira",
        cwd / "automation" / "jira" / ".env.jira",
        cwd / "automation" / "jira" / ".env.jira.sample",
    ]
    for p in candidates:
        load_env_file(p)


def main() -> None:
    preload_env()
    args = parse_args()
    m = re.search(r"[A-Z]+-\d+", args.title)
    if not m:
        print("No Jira key in title. Skip.")
        return
    issue_key = m.group(0)

    jira_base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    jira_email = os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USER_EMAIL")
    jira_token = os.getenv("JIRA_API_KEY") or os.getenv("JIRA_API_TOKEN")

    notion_token = os.getenv("NOTION_TOKEN", "")
    notion_db = os.getenv("NOTION_DB_ID", "")

    summary = f"PR {args.event}: {args.title} {args.url}".strip()
    if args.dry_run:
        print(json.dumps({"issue_key": issue_key, "event": args.event, "summary": summary}, ensure_ascii=False, indent=2))
        return

    if not jira_base or not jira_email or not jira_token:
        raise SystemExit("Missing Jira env: JIRA_BASE_URL, JIRA_EMAIL(or USER_EMAIL), JIRA_API_KEY")

    headers = jira_headers(jira_base, jira_email, jira_token)
    add_jira_comment(jira_base, issue_key, headers, summary)

    if args.event == "opened":
        moved = transition_in_review(jira_base, issue_key, headers)
        print(f"Transitioned to In Review: {moved}")

    if args.event == "merged":
        moved = transition_done(jira_base, issue_key, headers)
        print(f"Transitioned to Done: {moved}")

    if notion_token and notion_db:
        upsert_notion_log(notion_token, notion_db, issue_key, args.event, summary)
        print("Notion log created")


if __name__ == "__main__":
    main()
