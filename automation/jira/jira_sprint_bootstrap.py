import argparse
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
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


def as_adf_text(text: str) -> Dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def slugify(text: str) -> str:
    allowed: List[str] = []
    for ch in text.lower().strip():
        if ch.isalnum():
            allowed.append(ch)
        elif ch in (" ", "-", "_"):
            allowed.append("-")
    compact = "".join(allowed)
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact.strip("-") or "task"


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def pick_issue_start_date(start_mode: str, sprint_start: datetime) -> str:
    if start_mode == "sprint_start":
        return sprint_start.date().isoformat()
    if start_mode == "none":
        return ""
    return datetime.now(timezone.utc).date().isoformat()


def resolve_settings(env: Mapping[str, str], cfg: Dict[str, Any], workspace: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    ws_cfg = (cfg.get("workspaces", {}) or {}).get(workspace, {})
    plan_cfg = plan.get("settings", {})

    def pick(*values: Any) -> Any:
        for value in values:
            if value is not None and value != "":
                return value
        return None

    settings = {
        "base_url": pick(env.get("JIRA_BASE_URL"), ws_cfg.get("jira_base_url")),
        "api_key": pick(env.get("JIRA_API_KEY"), ws_cfg.get("jira_api_key")),
        "email": pick(env.get("JIRA_USER_EMAIL"), env.get("JIRA_EMAIL"), ws_cfg.get("jira_email")),
        "project_key": pick(env.get("JIRA_PROJECT_KEY"), ws_cfg.get("jira_project_key"), plan.get("project_key")),
        "board_raw": pick(
            env.get("JIRA_BOARD_ID"),
            env.get("JIRA_TEAM_ID"),
            ws_cfg.get("jira_board_id"),
            plan_cfg.get("jira_board_id"),
        ),
        "story_points_field": pick(env.get("JIRA_STORY_POINTS_FIELD"), ws_cfg.get("story_points_field"), "customfield_10016"),
        "start_date_field": pick(env.get("JIRA_START_DATE_FIELD"), ws_cfg.get("start_date_field"), plan_cfg.get("start_date_field")),
        "start_date_mode": pick(env.get("JIRA_ISSUE_START_DATE_MODE"), ws_cfg.get("start_date_mode"), plan_cfg.get("start_date_mode"), "created_now"),
        "assignee_mode": pick(env.get("JIRA_ASSIGNEE_MODE"), ws_cfg.get("assignee_mode"), "me"),
        "assignee_account_id": pick(env.get("JIRA_ASSIGNEE_ACCOUNT_ID"), ws_cfg.get("assignee_account_id")),
        "gitlab_base_url": pick(env.get("GITLAB_BASE_URL"), ws_cfg.get("gitlab", {}).get("base_url")),
        "gitlab_token": pick(env.get("GITLAB_TOKEN"), ws_cfg.get("gitlab", {}).get("token")),
        "gitlab_project_id": pick(env.get("GITLAB_PROJECT_ID"), ws_cfg.get("gitlab", {}).get("project_id")),
        "gitlab_default_branch": pick(env.get("GITLAB_DEFAULT_BRANCH"), ws_cfg.get("gitlab", {}).get("default_branch"), "main"),
        "gitlab_create_branch": pick(env.get("GITLAB_CREATE_BRANCH"), ws_cfg.get("gitlab", {}).get("create_branch"), False),
    }
    return settings


def build_issue_fields(
    project_key: str,
    item: Dict[str, Any],
    assignee_account_id: Optional[str],
    start_date_field: Optional[str],
    start_date_value: str,
    parent_key: Optional[str],
) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "project": {"key": project_key},
        "summary": item["summary"],
        "description": as_adf_text(item.get("description", "")),
        "issuetype": {"name": item.get("issue_type", "Task")},
    }

    labels = list(item.get("labels", []))
    if labels:
        fields["labels"] = labels

    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}

    if parent_key:
        fields["parent"] = {"key": parent_key}

    if start_date_field and start_date_value:
        fields[start_date_field] = start_date_value

    return fields


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
                raise ValueError("JIRA_USER_EMAIL or JIRA_EMAIL is required for basic auth mode.")
            token = base64.b64encode(f"{email}:{api_key}".encode("utf-8")).decode("utf-8")
            self.session.headers["Authorization"] = f"Basic {token}"
        elif auth_mode == "bearer":
            self.session.headers["Authorization"] = f"Bearer {api_key}"
        else:
            raise ValueError("auth_mode must be 'basic' or 'bearer'.")

    @staticmethod
    def probe_auth_mode(base_url: str, api_key: str, email: Optional[str]) -> str:
        probe_url = f"{base_url.rstrip('/')}/rest/api/3/myself"
        headers = {"Accept": "application/json"}

        bearer_resp = requests.get(
            probe_url,
            headers={**headers, "Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if bearer_resp.status_code == 200:
            return "bearer"

        if email:
            token = base64.b64encode(f"{email}:{api_key}".encode("utf-8")).decode("utf-8")
            basic_resp = requests.get(
                probe_url,
                headers={**headers, "Authorization": f"Basic {token}"},
                timeout=20,
            )
            if basic_resp.status_code == 200:
                return "basic"

        raise RuntimeError(
            "Jira authentication failed for both bearer and basic. "
            "Check JIRA_API_KEY token validity and JIRA_EMAIL/JIRA_USER_EMAIL."
        )

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

    def find_board_id(self, project_key: str) -> int:
        if self.dry_run:
            print(f"[DRY-RUN] Resolve board id by project key: {project_key}")
            return 0
        data = self.request("GET", f"/rest/agile/1.0/board?projectKeyOrId={project_key}")
        values = data.get("values", [])
        if not values:
            raise RuntimeError(f"No board found for project key: {project_key}")
        return int(values[0]["id"])

    def get_myself(self) -> Dict[str, Any]:
        if self.dry_run:
            return {"accountId": "dry-run-account"}
        return self.request("GET", "/rest/api/3/myself")

    def create_sprint(self, name: str, board_id: int, start_date: datetime, end_date: datetime, goal: str) -> int:
        payload = {
            "name": name,
            "originBoardId": board_id,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "goal": goal,
        }
        data = self.request("POST", "/rest/agile/1.0/sprint", payload)
        if self.dry_run:
            return 999999
        return int(data["id"])

    def create_issue(self, fields: Dict[str, Any], project_key: str) -> str:
        data = self.request("POST", "/rest/api/3/issue", {"fields": fields})
        if self.dry_run:
            return f"{project_key}-DRY"
        return data["key"]

    def set_story_points(self, issue_key: str, story_points_field: str, points: float) -> None:
        payload = {"fields": {story_points_field: points}}
        self.request("PUT", f"/rest/api/3/issue/{issue_key}", payload)

    def add_issues_to_sprint(self, sprint_id: int, issue_keys: List[str]) -> None:
        self.request("POST", f"/rest/agile/1.0/sprint/{sprint_id}/issue", {"issues": issue_keys})

    def start_sprint(self, sprint_id: int, name: str, start_date: datetime, end_date: datetime, goal: str) -> None:
        payload = {
            "id": sprint_id,
            "name": name,
            "state": "active",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "goal": goal,
        }
        self.request("PUT", f"/rest/agile/1.0/sprint/{sprint_id}", payload)


class GitLabClient:
    def __init__(self, base_url: str, token: str, dry_run: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({"PRIVATE-TOKEN": token})

    def create_branch(self, project_id: str, branch_name: str, ref: str) -> Dict[str, Any]:
        encoded_project = quote_plus(str(project_id))
        path = f"/api/v4/projects/{encoded_project}/repository/branches"
        url = f"{self.base_url}{path}"
        payload = {"branch": branch_name, "ref": ref}
        if self.dry_run:
            print(f"[DRY-RUN] POST {url}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return {"web_url": f"{self.base_url}/{project_id}/-/tree/{branch_name}"}
        resp = self.session.post(url, data=payload, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"GitLab API error {resp.status_code} POST {path}: {resp.text}")
        return resp.json()


def create_issues_with_hierarchy(
    client: JiraClient,
    project_key: str,
    issues: List[Dict[str, Any]],
    story_points_field: str,
    assignee_account_id: Optional[str],
    start_date_field: Optional[str],
    start_date_value: str,
    gitlab_client: Optional[GitLabClient],
    gitlab_project_id: Optional[str],
    gitlab_default_branch: str,
    gitlab_create_branch: bool,
) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
    pending = [dict(issue) for issue in issues]
    created_keys: List[str] = []
    ref_to_key: Dict[str, str] = {}
    key_to_branch: Dict[str, str] = {}

    while pending:
        progressed = False
        next_round: List[Dict[str, Any]] = []

        for item in pending:
            ref = item.get("ref")
            parent_key = item.get("parent_key")
            parent_ref = item.get("parent_ref")
            if not parent_key and parent_ref:
                parent_key = ref_to_key.get(parent_ref)
                if not parent_key:
                    next_round.append(item)
                    continue

            fields = build_issue_fields(
                project_key=project_key,
                item=item,
                assignee_account_id=assignee_account_id,
                start_date_field=start_date_field,
                start_date_value=start_date_value,
                parent_key=parent_key,
            )

            key = client.create_issue(fields=fields, project_key=project_key)
            created_keys.append(key)
            if ref:
                ref_to_key[ref] = key

            points = item.get("story_points")
            if points is not None:
                client.set_story_points(key, story_points_field, float(points))

            print(f"Issue created: {key}")

            if gitlab_client and gitlab_project_id and gitlab_create_branch:
                branch_name = item.get("branch_name") or f"feature/{key}-{slugify(item['summary'])}"[:120]
                gitlab_client.create_branch(gitlab_project_id, branch_name, gitlab_default_branch)
                key_to_branch[key] = branch_name
                print(f"GitLab branch created: {branch_name}")

            progressed = True

        if not progressed and next_round:
            unresolved = [item.get("ref") or item.get("summary", "unknown") for item in next_round]
            raise RuntimeError(
                "Could not resolve parent hierarchy. Check parent_ref/parent_key values: " + ", ".join(unresolved)
            )

        pending = next_round

    return created_keys, ref_to_key, key_to_branch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and start a Jira sprint with configurable multi-project mapping.")
    parser.add_argument("--plan", default="jira_week_plan.sample.json", help="Path to sprint plan JSON file")
    parser.add_argument("--config", default="jira_automation.config.json", help="Path to workspace mapping config")
    parser.add_argument("--workspace", default="default", help="Workspace key from config")
    parser.add_argument("--live", action="store_true", help="Execute real Jira API calls. Default is dry-run.")
    parser.add_argument("--auth-mode", default=os.getenv("JIRA_AUTH_MODE", "auto"), choices=["auto", "bearer", "basic"])
    return parser.parse_args()


def main() -> None:
    cwd = Path(__file__).resolve().parent
    load_dotenv(cwd / ".env")
    args = parse_args()

    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = cwd / plan_path
    plan = load_json(plan_path)

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = cwd / config_path
    config = load_json(config_path)

    if args.workspace and args.workspace != "default":
        workspace = args.workspace
    else:
        workspace = plan.get("workspace") or args.workspace
    settings = resolve_settings(os.environ, config, workspace, plan)

    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    email = str(settings.get("email") or "").strip() or None
    board_raw = str(settings.get("board_raw") or "").strip()
    project_key = str(settings.get("project_key") or "").strip()
    story_points_field = str(settings.get("story_points_field") or "customfield_10016").strip()
    start_date_field = str(settings.get("start_date_field") or "").strip() or None
    start_date_mode = str(settings.get("start_date_mode") or "created_now").strip()
    assignee_mode = str(settings.get("assignee_mode") or "me").strip()
    assignee_account_id = str(settings.get("assignee_account_id") or "").strip() or None

    gitlab_base_url = str(settings.get("gitlab_base_url") or "").strip()
    gitlab_token = str(settings.get("gitlab_token") or "").strip()
    gitlab_project_id = str(settings.get("gitlab_project_id") or "").strip() or None
    gitlab_default_branch = str(settings.get("gitlab_default_branch") or "main").strip()
    gitlab_create_branch = normalize_bool(settings.get("gitlab_create_branch"))

    missing = []
    if not base_url:
        missing.append("JIRA_BASE_URL")
    if not api_key:
        missing.append("JIRA_API_KEY")
    if args.auth_mode == "basic" and not email:
        missing.append("JIRA_USER_EMAIL or JIRA_EMAIL")
    if not project_key:
        missing.append("JIRA_PROJECT_KEY")
    if missing:
        raise SystemExit("Missing required settings: " + ", ".join(missing))

    sprint_name = plan["sprint_name"]
    goal = plan.get("goal", "")
    days = int(plan.get("days", 7))
    issues = plan.get("issues", [])

    now = datetime.now(timezone.utc)
    start_date = now
    end_date = now + timedelta(days=days)

    selected_auth_mode = args.auth_mode
    if selected_auth_mode == "auto":
        if args.live:
            selected_auth_mode = JiraClient.probe_auth_mode(base_url, api_key, email)
        else:
            selected_auth_mode = "basic" if email else "bearer"

    client = JiraClient(
        base_url=base_url,
        api_key=api_key,
        email=email,
        auth_mode=selected_auth_mode,
        dry_run=not args.live,
    )

    if assignee_mode == "me" and not assignee_account_id:
        myself = client.get_myself()
        assignee_account_id = myself.get("accountId")

    gitlab_client: Optional[GitLabClient] = None
    if gitlab_base_url and gitlab_token:
        gitlab_client = GitLabClient(gitlab_base_url, gitlab_token, dry_run=not args.live)

    if board_raw:
        try:
            board_id = int(board_raw)
        except ValueError:
            print("JIRA_TEAM_ID/JIRA_BOARD_ID is not numeric. Trying auto board lookup by JIRA_PROJECT_KEY...")
            board_id = client.find_board_id(project_key)
    else:
        board_id = client.find_board_id(project_key)

    print(f"Mode: {'LIVE' if args.live else 'DRY-RUN'} / Auth: {selected_auth_mode} / Workspace: {workspace}")
    sprint_id = client.create_sprint(sprint_name, board_id, start_date, end_date, goal)
    print(f"Sprint created: {sprint_id}")

    issue_start_date = pick_issue_start_date(start_date_mode, start_date)
    created_issue_keys, ref_to_key, key_to_branch = create_issues_with_hierarchy(
        client=client,
        project_key=project_key,
        issues=issues,
        story_points_field=story_points_field,
        assignee_account_id=assignee_account_id,
        start_date_field=start_date_field,
        start_date_value=issue_start_date,
        gitlab_client=gitlab_client,
        gitlab_project_id=gitlab_project_id,
        gitlab_default_branch=gitlab_default_branch,
        gitlab_create_branch=gitlab_create_branch,
    )

    if created_issue_keys:
        client.add_issues_to_sprint(sprint_id, created_issue_keys)
        print(f"Added {len(created_issue_keys)} issues to sprint {sprint_id}")

    client.start_sprint(sprint_id, sprint_name, start_date, end_date, goal)
    print(f"Sprint started: {sprint_id}")

    if ref_to_key:
        print("Ref mapping:")
        print(json.dumps(ref_to_key, ensure_ascii=False, indent=2))

    if key_to_branch:
        print("GitLab branches:")
        print(json.dumps(key_to_branch, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
