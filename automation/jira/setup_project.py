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

TOOLKIT_REPO = "Seobway23/jira-toolkit"


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
    workflow_content = f"""\
name: Jira Sync
on:
  pull_request:
    types: [opened, closed]
jobs:
  sync:
    uses: {TOOLKIT_REPO}/.github/workflows/jira-sync-reusable.yml@main
    with:
      event_action: ${{{{ github.event.action }}}}
      pr_title: ${{{{ github.event.pull_request.title }}}}
      pr_url: ${{{{ github.event.pull_request.html_url }}}}
      pr_merged: ${{{{ toJson(github.event.pull_request.merged) }}}}
    secrets:
      JIRA_BASE_URL: ${{{{ secrets.JIRA_BASE_URL }}}}
      JIRA_EMAIL: ${{{{ secrets.JIRA_EMAIL }}}}
      JIRA_API_KEY: ${{{{ secrets.JIRA_API_KEY }}}}
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
