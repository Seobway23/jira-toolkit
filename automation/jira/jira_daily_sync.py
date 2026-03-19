import argparse
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import quote_plus

import requests


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().strip('"').strip("'")
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def resolve_settings(env: Mapping[str, str], cfg: Dict[str, Any], workspace: str) -> Dict[str, Any]:
    ws_cfg = (cfg.get("workspaces", {}) or {}).get(workspace, {})

    def pick(*values: Any) -> Any:
        for value in values:
            if value is not None and value != "":
                return value
        return None

    return {
        "jira_base_url": pick(env.get("JIRA_BASE_URL"), ws_cfg.get("jira_base_url")),
        "jira_api_key": pick(env.get("JIRA_API_KEY"), ws_cfg.get("jira_api_key")),
        "jira_email": pick(env.get("JIRA_USER_EMAIL"), env.get("JIRA_EMAIL"), ws_cfg.get("jira_email")),
        "jira_project_key": pick(env.get("JIRA_PROJECT_KEY"), ws_cfg.get("jira_project_key")),
        "jira_board_id": pick(env.get("JIRA_BOARD_ID"), ws_cfg.get("jira_board_id")),
        "gitlab_base_url": pick(env.get("GITLAB_BASE_URL"), ws_cfg.get("gitlab", {}).get("base_url"), "https://gitlab.com"),
        "gitlab_token": pick(env.get("GITLAB_TOKEN"), ws_cfg.get("gitlab", {}).get("token")),
        "gitlab_project_id": pick(env.get("GITLAB_PROJECT_ID"), ws_cfg.get("gitlab", {}).get("project_id")),
        "strict_done": pick(env.get("JIRA_DAILY_STRICT_DONE"), ws_cfg.get("strict_done"), False),
        "protected_labels": pick(env.get("JIRA_DAILY_PROTECTED_LABELS"), ws_cfg.get("protected_labels"), "blocked,manual-only,needs-qa"),
    }


class JiraClient:
    def __init__(self, base_url: str, api_key: str, email: Optional[str], auth_mode: str, dry_run: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.email = email
        self.auth_mode = auth_mode
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        if auth_mode == "basic":
            if not email:
                raise ValueError("JIRA_USER_EMAIL/JIRA_EMAIL is required for basic auth mode.")
            token = base64.b64encode(f"{email}:{api_key}".encode("utf-8")).decode("utf-8")
            self.session.headers["Authorization"] = f"Basic {token}"
        else:
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    @staticmethod
    def probe_auth_mode(base_url: str, api_key: str, email: Optional[str]) -> str:
        url = f"{base_url.rstrip('/')}/rest/api/3/myself"
        headers = {"Accept": "application/json"}
        bearer = requests.get(url, headers={**headers, "Authorization": f"Bearer {api_key}"}, timeout=20)
        if bearer.status_code == 200:
            return "bearer"
        if email:
            token = base64.b64encode(f"{email}:{api_key}".encode("utf-8")).decode("utf-8")
            basic = requests.get(url, headers={**headers, "Authorization": f"Basic {token}"}, timeout=20)
            if basic.status_code == 200:
                return "basic"
        raise RuntimeError("Jira auth failed for both bearer/basic")

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        if self.dry_run:
            print(f"[DRY-RUN] {method} {url}")
            if payload is not None:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            return {"dry_run": True}
        resp = self.session.request(method=method, url=url, data=json.dumps(payload) if payload is not None else None, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"Jira API error {resp.status_code} {method} {path}: {resp.text}")
        if not resp.text:
            return {}
        return resp.json()

    def search_open_issues(self, project_key: str) -> List[Dict[str, Any]]:
        jql = f"project = {project_key} AND assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
        path = f"/rest/api/3/search/jql?maxResults=100&fields=summary,status,labels,issuetype,parent&jql={quote_plus(jql)}"
        data = self.request("GET", path)
        return data.get("issues", [])

    def get_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        data = self.request("GET", f"/rest/api/3/issue/{issue_key}/comment?maxResults=100")
        return data.get("comments", [])

    def add_comment_if_absent(self, issue_key: str, marker: str, comment_text: str) -> bool:
        comments = self.get_comments(issue_key)
        for c in comments:
            body = c.get("body", {})
            if marker in json.dumps(body, ensure_ascii=False):
                return False
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": comment_text}]}
                ],
            }
        }
        self.request("POST", f"/rest/api/3/issue/{issue_key}/comment", payload)
        return True

    def update_labels(self, issue: Dict[str, Any], new_labels: List[str]) -> None:
        issue_key = issue["key"]
        fields = issue.get("fields", {})
        current = list(fields.get("labels", []))
        merged = sorted(set(current + new_labels))
        if merged == sorted(current):
            return
        self.request("PUT", f"/rest/api/3/issue/{issue_key}", {"fields": {"labels": merged}})

    def get_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        data = self.request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        return data.get("transitions", [])

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self.request("POST", f"/rest/api/3/issue/{issue_key}/transitions", {"transition": {"id": transition_id}})

    def health_check_board(self, board_id: Optional[str]) -> bool:
        if not board_id:
            return True
        try:
            self.request("GET", f"/rest/agile/1.0/board/{board_id}")
            return True
        except Exception:
            return False


class GitLabClient:
    def __init__(self, base_url: str, token: str, project_id: str, dry_run: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.project_id = project_id
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({"PRIVATE-TOKEN": token})

    def _get(self, path: str, params: Dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        if self.dry_run:
            print(f"[DRY-RUN] GET {url} params={params}")
            return []
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"GitLab API error {resp.status_code} GET {path}: {resp.text}")
        return resp.json()

    def collect_issue_evidence(self, issue_key: str, since: datetime, until: datetime) -> Dict[str, Any]:
        encoded = quote_plus(self.project_id)
        commits = self._get(
            f"/api/v4/projects/{encoded}/repository/commits",
            {
                "since": since.isoformat(),
                "until": until.isoformat(),
                "search": issue_key,
                "per_page": 100,
            },
        )
        mrs = self._get(
            f"/api/v4/projects/{encoded}/merge_requests",
            {
                "state": "all",
                "search": issue_key,
                "updated_after": since.isoformat(),
                "per_page": 50,
            },
        )
        merged_mrs = [mr for mr in mrs if mr.get("state") == "merged"]
        opened_mrs = [mr for mr in mrs if mr.get("state") in ("opened", "locked")]
        return {
            "commit_count": len(commits),
            "commits": commits,
            "mr_count": len(mrs),
            "merged_mr_count": len(merged_mrs),
            "open_mr_count": len(opened_mrs),
            "merged_mrs": merged_mrs,
        }


def pick_done_transition_id(transitions: List[Dict[str, Any]]) -> Optional[str]:
    done_keywords = ("done", "완료", "해결", "종료", "closed")
    for t in transitions:
        name = (t.get("name") or "").lower()
        if any(k in name for k in done_keywords):
            return t.get("id")
    return None


def format_daily_comment(marker: str, issue_key: str, ev: Dict[str, Any], strict_done: bool) -> str:
    return (
        f"{marker}\n"
        f"- issue: {issue_key}\n"
        f"- commits: {ev['commit_count']}\n"
        f"- merge requests: {ev['mr_count']} (merged={ev['merged_mr_count']}, open={ev['open_mr_count']})\n"
        f"- strict_done_mode: {strict_done}\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Jira sync from GitLab evidence (safe-by-default).")
    parser.add_argument("--config", default="jira_automation.config.json")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--auth-mode", default=os.getenv("JIRA_AUTH_MODE", "auto"), choices=["auto", "basic", "bearer"])
    parser.add_argument("--window-hours", type=int, default=24)
    return parser.parse_args()


def main() -> None:
    cwd = Path(__file__).resolve().parent
    load_dotenv(cwd / ".env")
    args = parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = cwd / cfg_path
    cfg = load_json(cfg_path)
    settings = resolve_settings(os.environ, cfg, args.workspace)

    jira_base = str(settings.get("jira_base_url") or "").strip()
    jira_key = str(settings.get("jira_api_key") or "").strip()
    jira_email = str(settings.get("jira_email") or "").strip() or None
    project_key = str(settings.get("jira_project_key") or "").strip()
    board_id = str(settings.get("jira_board_id") or "").strip() or None

    gitlab_base = str(settings.get("gitlab_base_url") or "").strip()
    gitlab_token = str(settings.get("gitlab_token") or "").strip()
    gitlab_project_id = str(settings.get("gitlab_project_id") or "").strip()
    strict_done = normalize_bool(settings.get("strict_done"))
    protected_labels = [x.strip() for x in str(settings.get("protected_labels") or "").split(",") if x.strip()]

    missing = []
    if not jira_base:
        missing.append("JIRA_BASE_URL")
    if not jira_key:
        missing.append("JIRA_API_KEY")
    if not project_key:
        missing.append("JIRA_PROJECT_KEY")
    if args.live and not gitlab_token:
        missing.append("GITLAB_TOKEN")
    if args.live and not gitlab_project_id:
        missing.append("GITLAB_PROJECT_ID")
    if missing:
        raise SystemExit("Missing required settings: " + ", ".join(missing))

    auth_mode = args.auth_mode
    if auth_mode == "auto":
        auth_mode = JiraClient.probe_auth_mode(jira_base, jira_key, jira_email) if args.live else ("basic" if jira_email else "bearer")

    jira = JiraClient(jira_base, jira_key, jira_email, auth_mode, dry_run=not args.live)
    gitlab = GitLabClient(gitlab_base, gitlab_token, gitlab_project_id, dry_run=not args.live)

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.window_hours)
    marker = f"[Daily GitLab Sync {now.date().isoformat()}]"

    print(f"Mode: {'LIVE' if args.live else 'DRY-RUN'} / Workspace: {args.workspace} / Auth: {auth_mode}")
    board_ok = jira.health_check_board(board_id)
    if not board_ok:
        print("WARN: Jira board access failed (possible 404/permission). Continuing with issue-level API fallback.")

    issues = jira.search_open_issues(project_key)
    print(f"Target issues: {len(issues)}")

    updated = 0
    transitioned = 0

    for issue in issues:
        issue_key = issue["key"]
        labels = list(issue.get("fields", {}).get("labels", []))
        if any(lb in labels for lb in protected_labels):
            continue

        ev = gitlab.collect_issue_evidence(issue_key, since=since, until=now)

        new_labels: List[str] = []
        if ev["commit_count"] > 0:
            new_labels.append("gl-active-today")
        else:
            new_labels.append("gl-no-activity")
        if ev["open_mr_count"] > 0:
            new_labels.append("gl-review-needed")
        if ev["merged_mr_count"] > 0:
            new_labels.append("gl-merged")

        jira.update_labels(issue, new_labels)
        comment_text = format_daily_comment(marker, issue_key, ev, strict_done)
        added = jira.add_comment_if_absent(issue_key, marker, comment_text)
        if added:
            updated += 1

        if strict_done and ev["merged_mr_count"] > 0 and ev["open_mr_count"] == 0:
            transitions = jira.get_transitions(issue_key)
            done_id = pick_done_transition_id(transitions)
            if done_id:
                jira.transition_issue(issue_key, done_id)
                transitioned += 1

    print(f"Updated issues (commented): {updated}")
    print(f"Transitioned to done: {transitioned}")


if __name__ == "__main__":
    main()
