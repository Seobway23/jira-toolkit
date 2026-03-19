"""
Jira 이슈 키 기반 브랜치 자동 생성 + push + PR 생성 스크립트.

사용법:
  python automation/jira/jira_branch_create.py --key SCRUM-42 --slug "add-login-api" --push
  python automation/jira/jira_branch_create.py --key SCRUM-42 --slug "add-login-api" --push --pr
  python automation/jira/jira_branch_create.py --key SCRUM-42 --slug "add-login-api" --dry-run

환경변수 (.env 또는 export):
  JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_KEY   ← Jira 상태 전환용
  GITHUB_TOKEN, GITHUB_REPO                 ← PR 생성용 (선택)
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# 환경변수 로드
# ---------------------------------------------------------------------------

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_key = key.strip().strip('"').strip("'")
        if not env_key or env_key in os.environ:
            continue
        os.environ[env_key] = value.strip().strip('"').strip("'")


def preload_env() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    for candidate in [
        repo_root / "front" / "ops-portal" / ".env",
        repo_root / ".env",
        Path.cwd() / ".env",
    ]:
        if candidate.exists():
            load_env_file(candidate)
            return


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 40) -> str:
    result = []
    for ch in text.lower().strip():
        if ch.isalnum():
            result.append(ch)
        elif ch in (" ", "-", "_"):
            result.append("-")
    compact = "".join(result)
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact.strip("-")[:max_len] or "task"


def branch_name(issue_type: str, key: str, slug: str) -> str:
    prefix_map = {
        "feature": "feature",
        "fix": "fix",
        "bug": "fix",
        "chore": "chore",
        "refactor": "refactor",
        "docs": "chore",
    }
    prefix = prefix_map.get(issue_type.lower(), "feature")
    return f"{prefix}/{key}-{slug}"


def run(cmd: list[str], dry_run: bool = False) -> int:
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        print("  [dry-run] skipped")
        return 0
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def git_branch_exists_local(branch: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "--list", branch],
        capture_output=True, text=True
    )
    return branch in result.stdout


def create_and_push_branch(branch: str, base: str, push: bool, dry_run: bool) -> bool:
    print(f"\n[git] 브랜치 생성: {branch} (base: {base})")

    if git_branch_exists_local(branch):
        print(f"  이미 존재하는 브랜치: {branch}")
        rc = run(["git", "checkout", branch], dry_run)
    else:
        rc = run(["git", "checkout", "-b", branch, f"origin/{base}"], dry_run)
        if rc != 0:
            rc = run(["git", "checkout", "-b", branch], dry_run)

    if rc != 0:
        print(f"  [오류] 브랜치 생성 실패 (exit {rc})")
        return False

    if push:
        print(f"\n[git] push: {branch}")
        rc = run(["git", "push", "-u", "origin", branch], dry_run)
        if rc != 0:
            print(f"  [오류] push 실패 (exit {rc})")
            return False

    return True


# ---------------------------------------------------------------------------
# Jira API
# ---------------------------------------------------------------------------

def jira_auth_header() -> str:
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_KEY", "")
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def jira_get_transitions(base_url: str, issue_key: str) -> list[dict]:
    url = f"{base_url}/rest/api/3/issue/{issue_key}/transitions"
    req = Request(url, headers={"Authorization": jira_auth_header(), "Accept": "application/json"})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("transitions", [])
    except Exception as e:
        print(f"  [경고] Jira transitions 조회 실패: {e}")
        return []


def jira_transition(base_url: str, issue_key: str, target_name: str, dry_run: bool) -> bool:
    transitions = jira_get_transitions(base_url, issue_key)
    tid = None
    for t in transitions:
        name = (t.get("name") or "").lower()
        if target_name.lower() in name:
            tid = t.get("id")
            break

    if not tid:
        available = [t.get("name") for t in transitions]
        print(f"  [경고] '{target_name}' 전환 없음. 가능한 상태: {available}")
        return False

    print(f"\n[jira] {issue_key} → {target_name} (transition id: {tid})")
    if dry_run:
        print("  [dry-run] skipped")
        return True

    url = f"{base_url}/rest/api/3/issue/{issue_key}/transitions"
    payload = json.dumps({"transition": {"id": tid}}).encode()
    req = Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": jira_auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    try:
        with urlopen(req, timeout=15) as resp:
            print(f"  완료 (HTTP {resp.status})")
            return True
    except HTTPError as e:
        print(f"  [오류] Jira 전환 실패: {e.code} {e.reason}")
        return False


# ---------------------------------------------------------------------------
# GitHub PR 생성
# ---------------------------------------------------------------------------

def github_create_pr(
    repo: str, token: str, branch: str, base: str,
    title: str, body: str, dry_run: bool
) -> str | None:
    print(f"\n[github] PR 생성: {title}")
    if dry_run:
        print("  [dry-run] skipped")
        return None

    url = f"https://api.github.com/repos/{repo}/pulls"
    payload = json.dumps({
        "title": title,
        "body": body,
        "head": branch,
        "base": base,
        "draft": False,
    }).encode()
    req = Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }
    )
    try:
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            pr_url = data.get("html_url", "")
            print(f"  PR 생성 완료: {pr_url}")
            return pr_url
    except HTTPError as e:
        body_err = e.read().decode(errors="replace") if hasattr(e, "read") else ""
        print(f"  [오류] PR 생성 실패: {e.code} {e.reason}\n  {body_err}")
        return None


def build_pr_body(key: str, summary: str) -> str:
    return f"""## 연관 Jira 이슈
- [{key}] {summary}

## 변경 사항
- (작성 필요)

## 테스트
- [ ] 로컬 동작 확인
- [ ] TypeScript 빌드 통과 (`npx tsc --noEmit`)
- [ ] 백엔드 응답 포맷 확인 (`{{"ok": true/false}}`)
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Jira 이슈 기반 브랜치 생성 + push + PR 자동화")
    p.add_argument("--key", required=True, help="Jira 이슈 키 (예: SCRUM-42)")
    p.add_argument("--slug", default="", help="브랜치 슬러그 (예: add-login-api). 미입력 시 --key만 사용")
    p.add_argument("--summary", default="", help="PR 제목/본문용 이슈 summary")
    p.add_argument("--type", default="feature", dest="issue_type",
                   choices=["feature", "fix", "bug", "chore", "refactor", "docs"],
                   help="브랜치 prefix 타입 (기본: feature)")
    p.add_argument("--base", default="main", help="base 브랜치 (기본: main)")
    p.add_argument("--push", action="store_true", help="원격 push 실행")
    p.add_argument("--pr", action="store_true", help="GitHub PR 자동 생성 (--push 필요)")
    p.add_argument("--transition", default="In Progress",
                   help="브랜치 생성 후 Jira 상태 전환 (기본: 'In Progress', 빈 값으로 비활성화)")
    p.add_argument("--dry-run", action="store_true", help="실제 실행 없이 예상 동작 출력")
    return p.parse_args()


def main() -> None:
    preload_env()
    args = parse_args()

    key = args.key.strip().upper()
    if not re.match(r"^[A-Z]+-\d+$", key):
        print(f"[오류] 유효하지 않은 Jira 키: {key} (예: SCRUM-42)")
        sys.exit(1)

    slug = args.slug.strip() or slugify(args.summary) if args.summary else key.lower().replace("-", "")
    branch = branch_name(args.issue_type, key, slug)
    summary = args.summary.strip() or f"{key} 작업"

    print(f"=== Jira Branch Create ===")
    print(f"  이슈 키:  {key}")
    print(f"  브랜치:   {branch}")
    print(f"  base:     {args.base}")
    print(f"  push:     {args.push}")
    print(f"  PR:       {args.pr}")
    print(f"  dry-run:  {args.dry_run}")
    print()

    # 1. 브랜치 생성 + push
    ok = create_and_push_branch(branch, args.base, args.push, args.dry_run)
    if not ok:
        sys.exit(1)

    # 2. Jira 상태 전환
    if args.transition:
        base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        if base_url:
            jira_transition(base_url, key, args.transition, args.dry_run)
        else:
            print("  [경고] JIRA_BASE_URL 없음 → Jira 상태 전환 건너뜀")

    # 3. GitHub PR 생성
    if args.pr:
        if not args.push and not args.dry_run:
            print("[경고] --pr은 --push와 함께 사용해야 합니다.")
        token = os.getenv("GITHUB_TOKEN", "")
        repo = os.getenv("GITHUB_REPO", "")
        if not token or not repo:
            print("[경고] GITHUB_TOKEN 또는 GITHUB_REPO 없음 → PR 생성 건너뜀")
        else:
            pr_title = f"{key}: {summary}"
            pr_body = build_pr_body(key, summary)
            github_create_pr(repo, token, branch, args.base, pr_title, pr_body, args.dry_run)

    print(f"\n완료: {branch}")


if __name__ == "__main__":
    main()
