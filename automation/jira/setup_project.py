# -*- coding: utf-8 -*-
"""
setup_project.py - 새 프로젝트에 Jira/GitHub Actions/Claude 자동화 주입

사용법:
  python setup_project.py --target C:/path/to/new-project
  python setup_project.py --target C:/path/to/new-project --dry-run
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 이 스크립트가 있는 hellomd 루트
TOOLKIT_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_args():
    p = argparse.ArgumentParser(description="새 프로젝트에 Jira 자동화 툴킷 주입")
    p.add_argument("--target", required=True, help="대상 프로젝트 루트 경로")
    p.add_argument("--dry-run", action="store_true", help="실제 복사 없이 미리보기")
    p.add_argument("--skip-hook", action="store_true", help="git hook 설치 건너뛰기")
    return p.parse_args()


def copy_item(src: Path, dst: Path, dry_run: bool):
    if not src.exists():
        print(f"  ⚠️  원본 없음 (스킵): {src}")
        return
    if dry_run:
        print(f"  [DRY] {src} → {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    print(f"  ✅ {dst}")


def create_env_example(target: Path, dry_run: bool):
    dst = target / ".env.example"
    if dst.exists():
        print(f"  ⏭️  이미 존재 (스킵): {dst}")
        return
    content = """# Jira 설정 (필수)
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_KEY=your_api_key_here
JIRA_PROJECT_KEY=SCRUM

# GitHub 설정
GITHUB_TOKEN=ghp_xxxx

# GitLab 설정 (GitLab 사용 시)
GITLAB_TOKEN=glpat-xxxx
GITLAB_PROJECT_MANAGEMENT_ID=your-group/your-project

# Notion 연동 (선택)
NOTION_TOKEN=
NOTION_DB_ID=
"""
    if dry_run:
        print(f"  [DRY] .env.example 생성")
        return
    dst.write_text(content, encoding="utf-8")
    print(f"  ✅ {dst}")


def update_gitignore(target: Path, dry_run: bool):
    gi = target / ".gitignore"
    entries = [".env", ".env.*", ".current-scrum-key"]
    if gi.exists():
        existing = gi.read_text(encoding="utf-8", errors="replace")
    else:
        existing = ""
    to_add = [e for e in entries if e not in existing]
    if not to_add:
        print(f"  ⏭️  .gitignore 이미 최신")
        return
    if dry_run:
        print(f"  [DRY] .gitignore에 추가: {to_add}")
        return
    with open(gi, "a", encoding="utf-8") as f:
        f.write("\n# ops-toolkit\n")
        for e in to_add:
            f.write(e + "\n")
    print(f"  ✅ .gitignore 업데이트: {to_add}")


def install_hook(target: Path, dry_run: bool):
    hook_script = target / "automation" / "jira" / "install_git_hook.py"
    if not hook_script.exists():
        print("  ⚠️  hook 스크립트 없음 (스킵)")
        return
    if dry_run:
        print(f"  [DRY] git hook 설치: {target}")
        return
    result = subprocess.run(
        [sys.executable, str(hook_script), "--repo", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode == 0:
        print(f"  ✅ git hook 설치 완료")
    else:
        print(f"  ⚠️  git hook 설치 실패: {result.stderr.strip()}")


def main():
    args = parse_args()
    target = Path(args.target).resolve()
    dry_run = args.dry_run

    if not target.exists():
        raise SystemExit(f"대상 경로가 없습니다: {target}")
    if not (target / ".git").exists():
        raise SystemExit(f"Git 저장소가 아닙니다: {target}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}🚀 ops-toolkit 주입 시작")
    print(f"  원본: {TOOLKIT_ROOT}")
    print(f"  대상: {target}\n")

    # 1. automation/jira/ 복사
    print("📁 automation/jira/ 복사")
    copy_item(TOOLKIT_ROOT / "automation" / "jira", target / "automation" / "jira", dry_run)

    # 2. GitHub Actions 워크플로우 복사
    print("\n📁 .github/workflows/ 복사")
    copy_item(TOOLKIT_ROOT / ".github" / "workflows", target / ".github" / "workflows", dry_run)

    # 3. Claude 규칙 복사
    print("\n📁 .claude/rules/ 복사")
    copy_item(TOOLKIT_ROOT / ".claude" / "rules", target / ".claude" / "rules", dry_run)

    # 4. .env.example 생성
    print("\n📄 .env.example 생성")
    create_env_example(target, dry_run)

    # 5. .gitignore 업데이트
    print("\n📄 .gitignore 업데이트")
    update_gitignore(target, dry_run)

    # 6. git hook 설치
    if not args.skip_hook:
        print("\n🔧 git hook 설치")
        install_hook(target, dry_run)

    print(f"\n{'[DRY RUN] ' if dry_run else ''}✅ 완료!\n")
    print("다음 단계:")
    print(f"  1. cp {target}/.env.example {target}/.env")
    print(f"  2. .env 파일 열어서 값 채우기")
    print(f"  3. GitHub Secrets 등록: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_KEY")
    print(f"  4. python automation/jira/test_jira_env.py")


if __name__ == "__main__":
    main()
