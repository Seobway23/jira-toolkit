import argparse
import os
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Install prepare-commit-msg hook for Jira commit prefix automation")
    p.add_argument("--repo", required=True, help="Target git repository path")
    p.add_argument(
        "--script",
        default=str(Path(__file__).resolve().parent / "prepare_commit_msg.py"),
        help="Absolute path to prepare_commit_msg.py",
    )
    return p.parse_args()


def run_git(repo: Path, args: list[str]) -> None:
    subprocess.check_call(["git", *args], cwd=str(repo))


def main() -> None:
    args = parse_args()
    repo = Path(args.repo).resolve()
    script = Path(args.script).resolve()

    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repo not found: {repo}")
    if not (repo / ".git").exists():
        raise SystemExit(f"Not a git repo: {repo}")
    if not script.exists() or not script.is_file():
        raise SystemExit(f"Script not found: {script}")

    hooks_dir = repo / ".githooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_file = hooks_dir / "prepare-commit-msg"
    escaped_script = str(script).replace("\\", "/")
    hook_content = (
        "#!/usr/bin/env sh\n"
        "set -e\n"
        f'python "{escaped_script}" "$1"\n'
    )
    hook_file.write_text(hook_content, encoding="utf-8")
    os.chmod(hook_file, 0o755)

    run_git(repo, ["config", "core.hooksPath", ".githooks"])

    print(f"Installed hook: {hook_file}")
    print("Configured git core.hooksPath=.githooks")


if __name__ == "__main__":
    main()
