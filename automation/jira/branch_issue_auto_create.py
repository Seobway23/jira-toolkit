# -*- coding: utf-8 -*-
"""
branch_issue_auto_create.py

GitHub Actions에서 새 브랜치 push 시 자동으로 Jira 이슈를 생성한다.
환경변수:
  JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_KEY  - GitHub Secrets
  JIRA_PROJECT_KEY                          - GitHub Secret (기본값 SCRUM)
  BRANCH_NAME                               - github.ref_name

브랜치명 파싱:
  feature/kpi-dashboard  → Story  "kpi dashboard"
  fix/login-null-crash   → Bug    "login null crash"
  chore/update-eslint    → Task   "update eslint"
"""

import base64
import os
import re
import sys

import requests

# ─── 설정 ─────────────────────────────────────────────────────────────────────

JIRA_BASE = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_KEY = os.getenv("JIRA_API_KEY", "")
JIRA_PROJECT = os.getenv("JIRA_PROJECT_KEY") or "SCRUM"
BRANCH_NAME = os.getenv("BRANCH_NAME", "")

PREFIX_TO_ISSUETYPE = {
    "feature": "Story",
    "fix": "Bug",
    "chore": "Task",
    "refactor": "Story",
    "hotfix": "Bug",
}

# ─── API 헬퍼 ─────────────────────────────────────────────────────────────────


def _headers() -> dict:
    auth = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_KEY}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def jira_get(path: str) -> dict:
    url = f"{JIRA_BASE}/rest/api/3/{path}"
    r = requests.get(url, headers=_headers(), timeout=20)
    print(f"  GET {path} → {r.status_code}")
    r.raise_for_status()
    return r.json()


def jira_post(path: str, body: dict) -> dict:
    url = f"{JIRA_BASE}/rest/api/3/{path}"
    r = requests.post(url, headers=_headers(), json=body, timeout=20)
    print(f"  POST {path} → {r.status_code}")
    if not r.ok:
        print(f"  Response: {r.text[:400]}")
    r.raise_for_status()
    return r.json()


def jira_agile_get(path: str) -> dict:
    url = f"{JIRA_BASE}/rest/agile/1.0/{path}"
    r = requests.get(url, headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


# ─── 검증 ─────────────────────────────────────────────────────────────────────


def verify_auth() -> str:
    """인증 확인 + 현재 사용자 displayName 반환"""
    me = jira_get("myself")
    return me.get("displayName", me.get("emailAddress", "?"))


# ─── Jira 조회 ────────────────────────────────────────────────────────────────


def resolve_project_key(preferred: str) -> str:
    try:
        r = jira_get(f"project/{preferred}")
        return r.get("key", preferred)
    except Exception:
        pass

    # 프로젝트 목록에서 자동 감지
    try:
        projects = jira_get("project?maxResults=50")
        vals = projects if isinstance(projects, list) else projects.get("values", [])
        if vals:
            key = vals[0]["key"]
            print(f"  [warn] '{preferred}' 없음 → 자동감지: '{key}' (전체: {[p['key'] for p in vals[:5]]})")
            return key
    except Exception as e:
        print(f"  [warn] 프로젝트 목록 조회 실패: {e}")

    return preferred


def get_active_sprint_id(project_key: str) -> int | None:
    try:
        boards = jira_agile_get(f"board?projectKeyOrId={project_key}&type=scrum")
        vals = boards.get("values", [])
        if not vals:
            return None
        board_id = vals[0]["id"]
        sprints = jira_agile_get(f"board/{board_id}/sprint?state=active")
        sprint_vals = sprints.get("values", [])
        if sprint_vals:
            print(f"  [info] Sprint: {sprint_vals[0]['name']} (id={sprint_vals[0]['id']})")
            return sprint_vals[0]["id"]
    except Exception as e:
        print(f"  [warn] Sprint 조회 실패: {e}")
    return None


def get_account_id() -> str | None:
    try:
        from urllib.parse import quote
        r = jira_get(f"user/search?query={quote(JIRA_EMAIL)}")
        return r[0]["accountId"] if r else None
    except Exception:
        return None


def get_epic_key(project_key: str) -> str | None:
    try:
        boards = jira_agile_get(f"board?projectKeyOrId={project_key}&type=scrum")
        vals = boards.get("values", [])
        if not vals:
            return None
        board_id = vals[0]["id"]
        epics = jira_agile_get(f"board/{board_id}/epic?done=false")
        epic_vals = epics.get("values", [])
        if epic_vals:
            print(f"  [info] Epic: {epic_vals[0]['key']} ({epic_vals[0].get('summary','')})")
            return epic_vals[0]["key"]
    except Exception as e:
        print(f"  [warn] Epic 조회 실패: {e}")
    return None


def get_issue_types(project_key: str) -> list[str]:
    try:
        r = jira_get(f"project/{project_key}")
        return [t["name"] for t in r.get("issueTypes", [])]
    except Exception:
        return []


# ─── Jira 이슈 생성 ────────────────────────────────────────────────────────────


def create_issue(summary: str, issue_type: str) -> dict:
    project_key = resolve_project_key(JIRA_PROJECT)
    sprint_id = get_active_sprint_id(project_key)
    account_id = get_account_id()
    epic_key = get_epic_key(project_key)

    available_types = get_issue_types(project_key)
    if available_types and issue_type not in available_types:
        fallback = next((t for t in ["Task", "Story", "Bug"] if t in available_types), available_types[0])
        print(f"  [warn] '{issue_type}' 없음 → '{fallback}' 사용 (가능: {available_types})")
        issue_type = fallback

    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "description": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": f"Auto-created from branch: {BRANCH_NAME}"}
            ]}],
        },
    }
    if sprint_id:
        fields["customfield_10020"] = {"id": sprint_id}
    if account_id:
        fields["assignee"] = {"accountId": account_id}
    if epic_key:
        fields["parent"] = {"key": epic_key}

    try:
        return jira_post("issue", {"fields": fields})
    except requests.HTTPError:
        if "parent" in fields:
            print("  [warn] Epic parent 실패 → Epic 없이 재시도")
            fields.pop("parent")
            return jira_post("issue", {"fields": fields})
        raise


def transition_in_progress(issue_key: str):
    try:
        data = jira_get(f"issue/{issue_key}/transitions")
        t = next(
            (t for t in data.get("transitions", [])
             if "progress" in t["name"].lower() or "진행" in t["name"]),
            None,
        )
        if t:
            jira_post(f"issue/{issue_key}/transitions", {"transition": {"id": t["id"]}})
            print(f"  → {issue_key} 상태: In Progress")
        else:
            print(f"  [warn] In Progress 전환 없음: {[t['name'] for t in data.get('transitions',[])]}")
    except Exception as e:
        print(f"  [warn] 상태 전환 실패: {e}")


# ─── 브랜치 파싱 ──────────────────────────────────────────────────────────────


def parse_branch(branch: str):
    m = re.match(r"^(feature|fix|chore|refactor|hotfix)/(.+)$", branch)
    if not m:
        return None, None, None
    prefix = m.group(1)
    slug = m.group(2)
    issue_type = PREFIX_TO_ISSUETYPE.get(prefix, "Task")
    summary = slug.replace("-", " ").replace("_", " ")
    return prefix, issue_type, summary


# ─── 메인 ─────────────────────────────────────────────────────────────────────


def main():
    print(f"JIRA_BASE_URL: {'set' if JIRA_BASE else 'MISSING'}")
    print(f"JIRA_EMAIL:    {'set' if JIRA_EMAIL else 'MISSING'}")
    print(f"JIRA_API_KEY:  {'set' if JIRA_API_KEY else 'MISSING'}")
    print(f"JIRA_PROJECT:  {JIRA_PROJECT}")
    print(f"BRANCH_NAME:   {BRANCH_NAME}")

    if not JIRA_BASE or not JIRA_EMAIL or not JIRA_API_KEY:
        print("[skip] Jira credentials missing")
        sys.exit(0)
    if not BRANCH_NAME:
        print("[skip] BRANCH_NAME not set")
        sys.exit(0)

    prefix, issue_type, summary = parse_branch(BRANCH_NAME)
    if not prefix:
        print(f"[skip] Branch '{BRANCH_NAME}' pattern not matched")
        sys.exit(0)

    # 인증 확인
    try:
        user = verify_auth()
        print(f"Auth OK: {user}")
    except Exception as e:
        print(f"::error::Jira auth failed: {e}")
        sys.exit(1)

    print(f"\nCreating Jira {issue_type}: '{summary}'")

    try:
        result = create_issue(summary, issue_type)
    except Exception as e:
        print(f"[ERROR] 이슈 생성 실패: {e}")
        print(f"::error::Jira issue creation failed: {type(e).__name__}: {e}")
        sys.exit(1)

    issue_key = result["key"]
    issue_url = f"{JIRA_BASE}/browse/{issue_key}"
    print(f"\nCreated: {issue_key}")
    print(f"URL:     {issue_url}")

    transition_in_progress(issue_key)
    print(f"\nNext commit prefix: '{issue_key}: <message>'")

    github_output = os.getenv("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"issue_key={issue_key}\n")
            f.write(f"issue_url={issue_url}\n")


if __name__ == "__main__":
    main()
