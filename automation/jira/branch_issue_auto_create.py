# -*- coding: utf-8 -*-
"""
branch_issue_auto_create.py

GitHub Actions에서 새 브랜치 push 시 자동으로 Jira 이슈를 생성한다.
환경변수:
  JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_KEY  - GitHub Secrets
  JIRA_PROJECT_KEY                          - GitHub Secret or env (기본값 SCRUM)
  BRANCH_NAME                               - github.ref_name

브랜치명 파싱:
  feature/kpi-dashboard  → Story  "kpi dashboard"
  fix/login-null-crash   → Bug    "login null crash"
  chore/update-eslint    → Task   "update eslint"
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# ─── 설정 ─────────────────────────────────────────────────────────────────────

JIRA_BASE = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_KEY = os.getenv("JIRA_API_KEY", "")
JIRA_PROJECT = os.getenv("JIRA_PROJECT_KEY") or "SCRUM"  # 빈 문자열도 SCRUM 폴백
BRANCH_NAME = os.getenv("BRANCH_NAME", "")

PREFIX_TO_ISSUETYPE = {
    "feature": "Story",
    "fix": "Bug",
    "chore": "Task",
    "refactor": "Story",
    "hotfix": "Bug",
}

# ─── API 헬퍼 ─────────────────────────────────────────────────────────────────


def _auth_header() -> str:
    return "Basic " + base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_KEY}".encode()).decode()


def _request(url: str, method: str = "GET", body: dict = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", _auth_header())
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        print(f"[HTTP {e.code}] {url}")
        print(f"  Response: {raw[:500]}")
        raise


def jira_api(method: str, path: str, body: dict = None) -> dict:
    """Jira REST API v3: /rest/api/3/..."""
    return _request(f"{JIRA_BASE}/rest/api/3/{path}", method, body)


def jira_agile(method: str, path: str, body: dict = None) -> dict:
    """Jira Agile API: /rest/agile/1.0/..."""
    return _request(f"{JIRA_BASE}/rest/agile/1.0/{path}", method, body)


# ─── Jira 조회 ────────────────────────────────────────────────────────────────


def get_active_sprint_id() -> int | None:
    try:
        boards = jira_agile("GET", f"board?projectKeyOrId={JIRA_PROJECT}&type=scrum")
        vals = boards.get("values", [])
        if not vals:
            print("[info] 활성 스크럼 보드 없음")
            return None
        board_id = vals[0]["id"]
        sprints = jira_agile("GET", f"board/{board_id}/sprint?state=active")
        sprint_vals = sprints.get("values", [])
        if sprint_vals:
            print(f"[info] 활성 스프린트: {sprint_vals[0]['name']} (id={sprint_vals[0]['id']})")
            return sprint_vals[0]["id"]
        return None
    except Exception as e:
        print(f"[warn] 스프린트 조회 실패: {e}")
        return None


def get_epic_key() -> str | None:
    try:
        boards = jira_agile("GET", f"board?projectKeyOrId={JIRA_PROJECT}&type=scrum")
        vals = boards.get("values", [])
        if not vals:
            return None
        board_id = vals[0]["id"]
        epics = jira_agile("GET", f"board/{board_id}/epic?done=false")
        epic_vals = epics.get("values", [])
        if epic_vals:
            print(f"[info] 에픽 연결: {epic_vals[0]['key']} ({epic_vals[0].get('summary', '')})")
            return epic_vals[0]["key"]
        return None
    except Exception as e:
        print(f"[warn] 에픽 조회 실패: {e}")
        return None


def get_account_id() -> str | None:
    try:
        r = jira_api("GET", f"user/search?query={urllib.parse.quote(JIRA_EMAIL)}")
        return r[0]["accountId"] if r else None
    except Exception as e:
        print(f"[warn] 사용자 조회 실패: {e}")
        return None


def resolve_project_key(preferred: str) -> str:
    """preferred 키가 없으면 Jira 내 첫 번째 프로젝트 키 자동 감지"""
    # 1) preferred 키 직접 확인
    try:
        r = jira_api("GET", f"project/{preferred}")
        return r.get("key", preferred)
    except urllib.error.HTTPError:
        pass  # 404 or other → fall through to auto-detect

    # 2) 프로젝트 목록에서 첫 번째 키 자동 감지 (GET /project → array 직접 반환)
    try:
        projects = jira_api("GET", "project?maxResults=50")
        # Jira v3: array 또는 {"values": [...]} 둘 다 대응
        if isinstance(projects, list):
            vals = projects
        else:
            vals = projects.get("values", [])
        if vals:
            key = vals[0]["key"]
            print(f"[warn] 프로젝트 '{preferred}' 없음 → 자동 감지: '{key}'")
            print(f"[info] 사용 가능한 프로젝트: {[p['key'] for p in vals[:5]]}")
            return key
    except Exception as e:
        print(f"[warn] 프로젝트 목록 조회 실패: {e}")

    print(f"[error] 프로젝트를 찾을 수 없음. JIRA_PROJECT_KEY secret을 올바른 키로 설정하세요.")
    return preferred


def get_issue_types(project_key: str) -> list[str]:
    """프로젝트에서 사용 가능한 이슈 타입 조회"""
    try:
        r = jira_api("GET", f"project/{project_key}")
        types = r.get("issueTypes", [])
        return [t["name"] for t in types]
    except Exception:
        return []


# ─── Jira 이슈 생성 ────────────────────────────────────────────────────────────


def create_issue(summary: str, issue_type: str) -> dict:
    project_key = resolve_project_key(JIRA_PROJECT)
    sprint_id = get_active_sprint_id()
    account_id = get_account_id()
    epic_key = get_epic_key()

    # 이슈 타입이 프로젝트에 없으면 Task로 폴백
    available_types = get_issue_types(project_key)
    if available_types and issue_type not in available_types:
        fallback = next((t for t in ["Task", "Story", "Bug"] if t in available_types), available_types[0])
        print(f"[warn] '{issue_type}' 타입 없음. '{fallback}'로 대체 (사용 가능: {available_types})")
        issue_type = fallback

    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"Auto-created from branch: {BRANCH_NAME}"}],
                }
            ],
        },
    }

    if sprint_id:
        fields["customfield_10020"] = {"id": sprint_id}  # Sprint field
    if account_id:
        fields["assignee"] = {"accountId": account_id}

    # Epic 연결 시도 (실패해도 이슈 생성은 계속)
    if epic_key:
        # Jira Cloud newer: parent field
        fields["parent"] = {"key": epic_key}

    try:
        result = jira_api("POST", "issue", {"fields": fields})
        return result
    except urllib.error.HTTPError:
        # Epic parent 필드 문제일 수 있음 — 제거하고 재시도
        if "parent" in fields:
            print("[warn] Epic parent 연결 실패. Epic 없이 재시도...")
            fields.pop("parent")
            return jira_api("POST", "issue", {"fields": fields})
        raise


def transition_in_progress(issue_key: str):
    try:
        transitions = jira_api("GET", f"issue/{issue_key}/transitions")
        t = next(
            (
                t for t in transitions.get("transitions", [])
                if "progress" in t["name"].lower() or "진행" in t["name"]
            ),
            None,
        )
        if t:
            jira_api("POST", f"issue/{issue_key}/transitions", {"transition": {"id": t["id"]}})
            print(f"  → {issue_key} 상태: In Progress")
        else:
            names = [t["name"] for t in transitions.get("transitions", [])]
            print(f"[warn] 'In Progress' 전환 없음. 사용 가능한 전환: {names}")
    except Exception as e:
        print(f"[warn] 상태 전환 실패: {e}")


# ─── 브랜치 파싱 ──────────────────────────────────────────────────────────────


def parse_branch(branch: str):
    """'feature/kpi-dashboard' → ('feature', 'Story', 'kpi dashboard')"""
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
        print("[skip] Jira credentials missing — set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_KEY in GitHub Secrets")
        sys.exit(0)

    if not BRANCH_NAME:
        print("[skip] BRANCH_NAME not set")
        sys.exit(0)

    prefix, issue_type, summary = parse_branch(BRANCH_NAME)
    if not prefix:
        print(f"[skip] Branch '{BRANCH_NAME}' does not match feature/fix/chore/refactor/hotfix")
        sys.exit(0)

    print(f"\nCreating Jira {issue_type}: '{summary}'")

    try:
        result = create_issue(summary, issue_type)
    except Exception as e:
        print(f"[ERROR] Jira 이슈 생성 실패: {e}")
        print(f"::error::Jira issue creation failed: {type(e).__name__}: {e}")
        sys.exit(1)

    issue_key = result["key"]
    issue_url = f"{JIRA_BASE}/browse/{issue_key}"
    print(f"\nCreated: {issue_key}")
    print(f"URL:     {issue_url}")

    transition_in_progress(issue_key)
    print(f"\nNext: use '{issue_key}: <message>' as your commit prefix")

    # Actions output으로 SCRUM 키 내보내기 (PR 생성 등에 활용 가능)
    github_output = os.getenv("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"issue_key={issue_key}\n")
            f.write(f"issue_url={issue_url}\n")


if __name__ == "__main__":
    main()
