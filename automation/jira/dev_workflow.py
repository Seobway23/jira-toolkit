# -*- coding: utf-8 -*-
"""
dev_workflow.py - Jira + Git + GitHub/GitLab PR/MR 자동화 스크립트

사용법:
  python dev_workflow.py create-issue   # Jira 이슈 생성 + 브랜치 자동 생성
  python dev_workflow.py create-mr      # 현재 브랜치로 PR/MR 생성 (플랫폼 자동 감지)
  python dev_workflow.py full           # 이슈 생성 + 브랜치 + PR/MR 한번에

환경변수 (.env 파일):
  JIRA_EMAIL, JIRA_API_KEY, JIRA_BASE_URL, JIRA_PROJECT_KEY
  GITHUB_TOKEN                          # GitHub 사용 시
  GITLAB_TOKEN, GITLAB_PROJECT_MANAGEMENT_ID  # GitLab 사용 시
"""

import os, re, sys, json, subprocess, urllib.request, urllib.parse, base64

# Windows 터미널 UTF-8 출력
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime

# ─── .env 로드 ────────────────────────────────────────────────────────────────
# 우선순위: 스크립트 폴더(.env) → 스크립트 상위 폴더 → git 루트 → 현재 디렉토리
# jira-toolkit/.env 하나만 관리하면 모든 프로젝트에서 공유 가능

def _parse_env_file(path: Path) -> dict:
    env = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return env


def load_env() -> dict:
    script_dir = Path(__file__).resolve().parent

    candidates = [
        script_dir / ".env",           # jira-toolkit/automation/jira/.env
        script_dir.parent.parent / ".env",  # jira-toolkit/.env
        Path.cwd() / ".env",           # 현재 프로젝트 루트 .env (fallback)
    ]

    # git 루트도 후보에 추가
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, encoding="utf-8", errors="replace"
        ).strip()
        candidates.append(Path(git_root) / ".env")
    except Exception:
        pass

    env = {}
    loaded_from = None
    for path in candidates:
        if path.exists():
            env = _parse_env_file(path)
            loaded_from = path
            break

    if not env:
        print("[ERROR] .env 파일을 찾을 수 없습니다.")
        print("찾은 위치:")
        for c in candidates:
            print(f"  {c}")
        print("\n→ jira-toolkit/automation/jira/.env 또는 jira-toolkit/.env 에 생성하세요.")
        print("  cp automation/jira/env.example automation/jira/.env")
        sys.exit(1)

    print(f"[.env] {loaded_from}")
    return env


ENV = load_env()

# ─── Jira 설정 ────────────────────────────────────────────────────────────────

JIRA_BASE = ENV.get("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = ENV.get("JIRA_EMAIL", "")
JIRA_API_KEY = ENV.get("JIRA_API_KEY", "")
JIRA_PROJECT = ENV.get("JIRA_PROJECT_KEY", "SCRUM")
JIRA_AUTH = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_KEY}".encode()).decode()

# ─── Git 플랫폼 설정 ──────────────────────────────────────────────────────────

GITHUB_TOKEN = ENV.get("GITHUB_TOKEN", "")
GITLAB_TOKEN = ENV.get("GITLAB_TOKEN", "")
GITLAB_PROJECT_PATH = ENV.get("GITLAB_PROJECT_MANAGEMENT_ID", "")
GITLAB_PROJECT_ID: int = 0  # 아래에서 동적으로 조회


# ─── 유틸 ─────────────────────────────────────────────────────────────────────

def slugify(text: str, max_len: int = 40) -> str:
    """한글/특수문자 → 영문 슬러그 (간단 변환)"""
    import re
    text = text.lower().replace(" ", "-")
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len]


def run(cmd: str, cwd: str = None) -> str:
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result.stdout.strip()


def jira_request(method: str, path: str, body: dict = None):
    url = f"{JIRA_BASE}/rest/api/3/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Basic {JIRA_AUTH}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw.strip() else {}


def detect_remote_platform() -> tuple[str, str, str]:
    """
    git remote URL에서 플랫폼과 owner/repo 자동 감지.
    반환: (platform, owner, repo)
    platform = "github" | "gitlab" | "unknown"
    """
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True, encoding="utf-8", errors="replace"
        ).strip()
    except Exception:
        return "unknown", "", ""

    # SSH: git@github.com:owner/repo.git
    ssh_match = re.match(r"git@([\w.]+):([\w.\-]+)/([\w.\-]+?)(?:\.git)?$", remote_url)
    if ssh_match:
        host, owner, repo = ssh_match.group(1), ssh_match.group(2), ssh_match.group(3)
    else:
        # HTTPS: https://github.com/owner/repo.git
        https_match = re.match(r"https?://([\w.]+)/([\w.\-]+)/([\w.\-]+?)(?:\.git)?$", remote_url)
        if https_match:
            host, owner, repo = https_match.group(1), https_match.group(2), https_match.group(3)
        else:
            return "unknown", "", ""

    if "github.com" in host:
        return "github", owner, repo
    if "gitlab.com" in host:
        return "gitlab", owner, repo
    return "unknown", owner, repo


def github_request(method: str, path: str, body: dict = None):
    url = f"https://api.github.com/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            detail = json.loads(raw)
            msgs = [err.get("message", "") for err in detail.get("errors", [])]
            raise SystemExit(f"GitHub API {e.code}: {detail.get('message')} — {', '.join(msgs)}")
        except (json.JSONDecodeError, KeyError):
            raise SystemExit(f"GitHub API {e.code}: {raw[:200]}")


def gitlab_request(method: str, path: str, body: dict = None):
    global GITLAB_PROJECT_ID
    if not GITLAB_PROJECT_ID and "projects/" not in path:
        encoded = urllib.parse.quote(GITLAB_PROJECT_PATH, safe="")
        r = gitlab_request("GET", f"projects/{encoded}")
        GITLAB_PROJECT_ID = r["id"]

    url = f"https://gitlab.com/api/v4/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("PRIVATE-TOKEN", GITLAB_TOKEN)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw.strip() else {}


# ─── Jira 관련 ────────────────────────────────────────────────────────────────

def get_active_sprint_id() -> int | None:
    try:
        boards = jira_request("GET", f"agile/1.0/board?projectKeyOrId={JIRA_PROJECT}")
        board_id = boards["values"][0]["id"]
        sprints = jira_request("GET", f"agile/1.0/board/{board_id}/sprint?state=active")
        return sprints["values"][0]["id"] if sprints.get("values") else None
    except Exception:
        return None


def get_account_id() -> str | None:
    try:
        r = jira_request("GET", f"user/search?query={JIRA_EMAIL}")
        return r[0]["accountId"] if r else None
    except Exception:
        return None


def create_jira_issue(
    summary: str,
    description: str = "",
    issue_type: str = "Story",
    story_points: int = 3,
) -> dict:
    """Jira 이슈 생성 → {"key": "SCRUM-38", "url": "..."}"""
    sprint_id = get_active_sprint_id()
    account_id = get_account_id()
    today = datetime.now().strftime("%Y-%m-%d")

    fields: dict = {
        "project": {"key": JIRA_PROJECT},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": description or summary}]}
            ],
        },
        "customfield_10016": story_points,  # Story point estimate
        "customfield_10015": today,         # Start date
    }

    if sprint_id:
        fields["customfield_10020"] = {"id": sprint_id}
    if account_id:
        fields["assignee"] = {"accountId": account_id}

    result = jira_request("POST", "issue", {"fields": fields})
    issue_key = result["key"]
    issue_url = f"{JIRA_BASE}/browse/{issue_key}"

    # 상태 → 진행 중
    try:
        transitions = jira_request("GET", f"issue/{issue_key}/transitions")
        in_progress = next(
            (t for t in transitions["transitions"] if "진행" in t["name"] or "progress" in t["name"].lower()),
            None,
        )
        if in_progress:
            jira_request("POST", f"issue/{issue_key}/transitions", {"transition": {"id": in_progress["id"]}})
    except Exception:
        pass

    return {"key": issue_key, "url": issue_url}


def transition_jira_to_review(issue_key: str):
    """Jira 이슈 → 검토 중"""
    try:
        transitions = jira_request("GET", f"issue/{issue_key}/transitions")
        review = next(
            (t for t in transitions["transitions"] if "검토" in t["name"] or "review" in t["name"].lower()),
            None,
        )
        if review:
            jira_request("POST", f"issue/{issue_key}/transitions", {"transition": {"id": review["id"]}})
            print(f"  ✅ Jira 상태 → 검토 중")
    except Exception as e:
        print(f"  ⚠️  Jira 상태 전환 실패: {e}")


# ─── Git 관련 ─────────────────────────────────────────────────────────────────

def get_repo_root() -> str:
    return run("git rev-parse --show-toplevel")


def get_current_branch() -> str:
    return run("git branch --show-current")


def create_branch(issue_key: str, slug: str, issue_type: str = "feature", base: str = "main") -> str:
    prefix_map = {
        "story": "feature",
        "bug": "fix",
        "task": "chore",
        "subtask": "chore",
    }
    prefix = prefix_map.get(issue_type.lower(), "feature")
    # 브랜치명은 기능 단위 (SCRUM 키 제외) — SCRUM 키는 커밋 메시지에만 포함
    branch = f"{prefix}/{slug}"
    root = get_repo_root()

    run(f"git fetch origin {base}", cwd=root)
    run(f"git checkout -b {branch} origin/{base}", cwd=root)

    # 현재 작업 이슈 키 파일에 기록
    key_file = Path(root) / ".current-scrum-key"
    key_file.write_text(issue_key, encoding="utf-8")
    print(f"  ✅ 브랜치 생성: {branch}")
    print(f"  ✅ .current-scrum-key = {issue_key}")
    return branch


# ─── PR/MR 생성 (플랫폼 자동 감지) ───────────────────────────────────────────

def create_pr(
    source_branch: str,
    target_branch: str = "main",
    title: str = "",
    description: str = "",
) -> str:
    """git remote URL을 읽어 GitHub/GitLab 자동 판별 후 PR/MR 생성."""
    platform, owner, repo = detect_remote_platform()

    if not title:
        title = source_branch

    if platform == "github":
        if not GITHUB_TOKEN:
            raise SystemExit("GITHUB_TOKEN이 .env에 없습니다.")
        result = github_request(
            "POST",
            f"repos/{owner}/{repo}/pulls",
            {"title": title, "body": description, "head": source_branch, "base": target_branch},
        )
        return result["html_url"]

    if platform == "gitlab":
        global GITLAB_PROJECT_ID
        if not GITLAB_PROJECT_ID:
            encoded = urllib.parse.quote(GITLAB_PROJECT_PATH, safe="")
            r = gitlab_request("GET", f"projects/{encoded}")
            GITLAB_PROJECT_ID = r["id"]
        result = gitlab_request(
            "POST",
            f"projects/{GITLAB_PROJECT_ID}/merge_requests",
            {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
                "remove_source_branch": True,
            },
        )
        return result["web_url"]

    raise SystemExit(f"지원하지 않는 플랫폼입니다. remote URL을 확인하세요.")


# ─── CLI 흐름 ─────────────────────────────────────────────────────────────────

def cmd_create_issue():
    print("\n📋 Jira 이슈 생성")
    summary = input("  이슈 제목: ").strip()
    desc = input("  설명 (Enter 스킵): ").strip()
    itype = input("  타입 [Story/Bug/Task] (기본 Story): ").strip() or "Story"
    pts = input("  스토리 포인트 (기본 3): ").strip()
    story_points = int(pts) if pts.isdigit() else 3

    print("  ⏳ Jira 이슈 생성 중...")
    issue = create_jira_issue(summary, desc, itype, story_points)
    print(f"  ✅ 이슈 생성: {issue['key']} — {issue['url']}")

    slug_input = input(f"  브랜치 슬러그 (기본: {slugify(summary)}): ").strip()
    slug = slug_input or slugify(summary)
    base = input("  base 브랜치 (기본: dev): ").strip() or "dev"

    branch = create_branch(issue["key"], slug, itype, base)
    print(f"\n  다음 단계:")
    print(f"    1. 코드 작성 후: git add . && git commit -m \"{issue['key']}: <내용>\"")
    print(f"    2. 푸시: git push -u origin {branch}")
    print(f"    3. MR 생성: python dev_workflow.py create-mr")


def extract_jira_keys_from_commits(base: str = "main") -> list[str]:
    """최근 커밋 메시지에서 SCRUM 키 추출 (브랜치 분기 이후 커밋만)"""
    try:
        out = run(f"git log {base}..HEAD --format=%s")
        keys = []
        seen = set()
        for line in out.splitlines():
            for m in re.findall(r"[A-Z]+-\d+", line):
                if m not in seen:
                    keys.append(m)
                    seen.add(m)
        return keys
    except Exception:
        return []


def cmd_create_mr():
    platform, owner, repo = detect_remote_platform()
    label = "PR" if platform == "github" else "MR"
    print(f"\n🔀 {platform.upper()} {label} 생성 ({owner}/{repo})")
    branch = get_current_branch()
    print(f"  현재 브랜치: {branch}")

    # 커밋 메시지에서 SCRUM 키 추출 (새 브랜치 전략 대응)
    keys = extract_jira_keys_from_commits()
    if not keys:
        # fallback: 브랜치명에서 추출
        match = re.search(r"([A-Z]+-\d+)", branch, re.IGNORECASE)
        keys = [match.group(1).upper()] if match else []

    keys_str = ", ".join(keys) if keys else "없음"
    print(f"  감지된 Jira 이슈: {keys_str}")

    default_target = "main" if platform == "github" else "dev"
    target = input(f"  target 브랜치 (기본: {default_target}): ").strip() or default_target
    default_title = f"feature: {branch.split('/')[-1]} ({', '.join(keys)})" if keys else branch
    title = input(f"  {label} 제목 (기본: {default_title}): ").strip() or default_title
    desc = input("  설명 (Enter 스킵): ").strip()

    if not desc:
        issues_list = "\n".join(f"- {k}" for k in keys) if keys else "- (없음)"
        desc = f"## Related Issues\n{issues_list}\n\n🤖 Generated with Claude Code"

    print(f"  ⏳ {label} 생성 중...")
    url = create_pr(branch, target, title, desc)
    print(f"  ✅ {label} 생성 완료: {url}")

    # 연관된 모든 Jira 이슈를 In Review로 전환
    for key in keys:
        transition_jira_to_review(key)


def cmd_full():
    print("\n🚀 Full 워크플로우: Jira → 브랜치 → (코드 작업 후) → MR")
    cmd_create_issue()
    input("\n  코드 작업 후 Enter를 눌러 MR 생성을 진행하세요...")
    cmd_create_mr()


# ─── 진입점 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "create-issue":
        cmd_create_issue()
    elif cmd == "create-mr":
        cmd_create_mr()
    elif cmd == "full":
        cmd_full()
    else:
        print(__doc__)
