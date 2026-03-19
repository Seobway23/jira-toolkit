# -*- coding: utf-8 -*-
"""
setup_project.py - 새 프로젝트에 jira-toolkit 참조 설정

복사 없음. jira.config.json + 5줄 GitHub Actions caller만 생성.

사용법:
  python setup_project.py --target /path/to/your-project
  python setup_project.py --target /path/to/your-project --project-key MYPROJECT
"""
import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def detect_toolkit_repo() -> str:
    """이 스크립트가 있는 jira-toolkit의 git remote URL에서 owner/repo 자동 감지."""
    try:
        script_dir = Path(__file__).resolve().parent.parent.parent  # jira-toolkit 루트
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=str(script_dir), text=True, encoding="utf-8", errors="replace"
        ).strip()
        m = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?$", remote)
        if m:
            return m.group(1)
        m = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", remote)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "Seobway23/jira-toolkit"  # fallback


TOOLKIT_REPO = detect_toolkit_repo()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True, help="대상 프로젝트 루트 경로")
    p.add_argument("--project-key", default="SCRUM", help="Jira 프로젝트 키 (기본: SCRUM)")
    p.add_argument("--branch", default="main", help="기본 타겟 브랜치 (기본: main)")
    return p.parse_args()


def main():
    args = parse_args()
    target = Path(args.target).resolve()

    if not target.exists():
        raise SystemExit(f"경로 없음: {target}")
    if not (target / ".git").exists():
        raise SystemExit(f"Git 저장소가 아님: {target}")

    # 1. jira.config.json 생성
    config_path = target / "jira.config.json"
    config = {
        "toolkit": TOOLKIT_REPO,
        "jira_project_key": args.project_key,
        "default_branch": args.branch,
    }
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {config_path}")

    # 2. GitHub Actions caller 생성
    workflow_dir = target / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = workflow_dir / "jira.yml"
    workflow_content = """\
name: Jira Sync
on:
  pull_request:
    types: [opened, closed]
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install requests
      - name: Sync to Jira
        env:
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_KEY: ${{ secrets.JIRA_API_KEY }}
          NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
          NOTION_DB_ID: ${{ secrets.NOTION_DB_ID }}
          GITHUB_EVENT_ACTION: ${{ github.event.action }}
          GITHUB_PR_TITLE: ${{ github.event.pull_request.title }}
          GITHUB_PR_URL: ${{ github.event.pull_request.html_url }}
          GITHUB_PR_MERGED: ${{ toJson(github.event.pull_request.merged) }}
        run: |
          TOOLKIT=$(python -c "import json; print(json.load(open('jira.config.json'))['toolkit'])")
          BASE="https://raw.githubusercontent.com/$TOOLKIT/main/automation/jira"
          curl -sSfL "$BASE/pr_event_sync.py" -o pr_event_sync.py
          curl -sSfL "$BASE/ci_pr_event_entrypoint.py" -o ci_pr_event_entrypoint.py
          python ci_pr_event_entrypoint.py --source github
"""
    workflow_path.write_text(workflow_content, encoding="utf-8")
    print(f"✅ {workflow_path}")

    # 3. .gitignore에 .current-scrum-key 추가
    gi = target / ".gitignore"
    existing = gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""
    if ".current-scrum-key" not in existing:
        with open(gi, "a", encoding="utf-8") as f:
            f.write("\n.current-scrum-key\n")
        print(f"✅ .gitignore 업데이트")

    print(f"""
완료! 다음 단계:
  1. GitHub Secrets 등록 (Settings → Secrets → Actions):
     JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_KEY

  2. 스크립트 실행 시:
     python {Path(__file__).resolve().parent}/dev_workflow.py create-mr
""")


if __name__ == "__main__":
    main()
