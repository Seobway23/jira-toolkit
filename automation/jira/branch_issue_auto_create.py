# -*- coding: utf-8 -*-
"""
branch_issue_auto_create.py

GitHub Actions에서 새 브랜치 push 시 자동으로 Jira 이슈를 생성한다.
환경변수:
  JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_KEY  - GitHub Secrets로 주입
  BRANCH_NAME                               - github.ref_name

브랜치명 파싱:
  feature/kpi-dashboard  →  Story  "kpi dashboard"
  fix/login-null-crash   →  Bug    "login null crash"
  chore/update-eslint    →  Task   "update eslint"
  refactor/route-split   →  Story  "route split"
"""

import base64
import json
import os
import re
import sys
import urllib.request

# ─── 설정 ─────────────────────────────────────────────────────────────────────

JIRA_BASE = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_KEY = os.getenv("JIRA_API_KEY", "")
JIRA_PROJECT = os.getenv("JIRA_PROJECT_KEY", "SCRUM")

BRANCH_NAME = os.getenv("BRANCH_NAME", "")

PREFIX_TO_ISSUETYPE = {
    "feature": "Story",
    "fix": "Bug",
    "chore": "Task",
    "refactor": "Story",
    "hotfix": "Bug",
}

# ─── 유틸 ─────────────────────────────────────────────────────────────────────


def jira_auth_header() -> str:
    return "Basic " + base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_KEY}".encode()).decode()


def jira_request(method: str, path: str, body: dict = None):
    url = f"{JIRA_BASE}/rest/api/3/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", jira_auth_header())
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        print(f"[Jira API Error] {e.code}: {raw[:300]}", file=sys.stderr)
        raise


def parse_branch(branch: str):
    """
    'feature/kpi-dashboard' → ('feature', 'Story', 'kpi dashboard')
    returns (prefix, issue_type, summary)
    """
    m = re.match(r"^(feature|fix|chore|refactor|hotfix)/(.+)$", branch)
    if not m:
        return None, None, None
    prefix = m.group(1)
    slug = m.group(2)
    issue_type = PREFIX_TO_ISSUETYPE.get(prefix, "Story")
    summary = slug.replace("-", " ").replace("_", " ")
    return prefix, issue_type, summary


def get_epic_key() -> str | None:
    """활성 스프린트에서 첫 번째 Epic 키 반환"""
    try:
        boards = jira_request("GET", f"agile/1.0/board?projectKeyOrId={JIRA_PROJECT}")
        if not boards.get("values"):
            return None
        board_id = boards["values"][0]["id"]
        # 현재 스프린트 에픽 조회
        epics = jira_request("GET", f"agile/1.0/board/{board_id}/epic?done=false")
        vals = epics.get("values", [])
        return vals[0]["key"] if vals else None
    except Exception as e:
        print(f"[warn] 에픽 조회 실패: {e}")
        return None


def get_active_sprint_id() -> int | None:
    try:
        boards = jira_request("GET", f"agile/1.0/board?projectKeyOrId={JIRA_PROJECT}")
        if not boards.get("values"):
            return None
        board_id = boards["values"][0]["id"]
        sprints = jira_request("GET", f"agile/1.0/board/{board_id}/sprint?state=active")
        vals = sprints.get("values", [])
        return vals[0]["id"] if vals else None
    except Exception as e:
        print(f"[warn] 활성 스프린트 조회 실패: {e}")
        return None


def get_account_id() -> str | None:
    try:
        r = jira_request("GET", f"user/search?query={JIRA_EMAIL}")
        return r[0]["accountId"] if r else None
    except Exception:
        return None


def create_issue(summary: str, issue_type: str) -> dict:
    sprint_id = get_active_sprint_id()
    account_id = get_account_id()

    fields = {
        "project": {"key": JIRA_PROJECT},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Auto-created from branch: {BRANCH_NAME}",
                        }
                    ],
                }
            ],
        },
    }
    if sprint_id:
        fields["customfield_10020"] = {"id": sprint_id}
    if account_id:
        fields["assignee"] = {"accountId": account_id}

    epic_key = get_epic_key()
    if epic_key:
        # Jira Cloud: customfield_10014 = Epic Link
        fields["customfield_10014"] = epic_key
        print(f"  Epic 연결: {epic_key}")

    result = jira_request("POST", "issue", {"fields": fields})
    return result


def transition_in_progress(issue_key: str):
    try:
        transitions = jira_request("GET", f"issue/{issue_key}/transitions")
        t = next(
            (
                t
                for t in transitions.get("transitions", [])
                if "progress" in t["name"].lower() or "진행" in t["name"]
            ),
            None,
        )
        if t:
            jira_request("POST", f"issue/{issue_key}/transitions", {"transition": {"id": t["id"]}})
            print(f"  Transitioned {issue_key} → In Progress")
    except Exception as e:
        print(f"  [warn] 상태 전환 실패: {e}")


# ─── 메인 ─────────────────────────────────────────────────────────────────────


def main():
    if not JIRA_BASE or not JIRA_EMAIL or not JIRA_API_KEY:
        print("[skip] Jira credentials not set (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_KEY)")
        sys.exit(0)

    if not BRANCH_NAME:
        print("[skip] BRANCH_NAME not set")
        sys.exit(0)

    prefix, issue_type, summary = parse_branch(BRANCH_NAME)
    if not prefix:
        print(f"[skip] Branch '{BRANCH_NAME}' does not match feature/fix/chore/refactor/hotfix pattern")
        sys.exit(0)

    print(f"Branch: {BRANCH_NAME}")
    print(f"Creating Jira {issue_type}: '{summary}'")

    result = create_issue(summary, issue_type)
    issue_key = result["key"]
    issue_url = f"{JIRA_BASE}/browse/{issue_key}"
    print(f"Created: {issue_key} — {issue_url}")

    transition_in_progress(issue_key)
    print(f"Done. Add '{issue_key}: ...' prefix to your commits.")


if __name__ == "__main__":
    main()
