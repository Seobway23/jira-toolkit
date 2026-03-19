import re
import subprocess
import sys
from pathlib import Path
from typing import List


def run(cmd: List[str]) -> str:
    return subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace").strip()


def get_current_scrum_key() -> str:
    """
    우선순위:
    1. 레포 루트의 .current-scrum-key 파일
    2. 브랜치명에서 추출 (하위 호환)
    """
    try:
        repo_root = Path(run(["git", "rev-parse", "--show-toplevel"]))
        key_file = repo_root / ".current-scrum-key"
        if key_file.exists():
            key = key_file.read_text(encoding="utf-8").strip()
            if re.match(r"[A-Z]+-\d+", key):
                return key
    except Exception:
        pass

    # fallback: 브랜치명에서 추출
    try:
        branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        m = re.search(r"[A-Z]+-\d+", branch)
        if m:
            return m.group(0)
    except Exception:
        pass

    return ""


def staged_files() -> List[str]:
    out = run(["git", "diff", "--cached", "--name-only"])
    return [x for x in out.splitlines() if x.strip()]


def infer_scope(files: List[str]) -> str:
    if not files:
        return "repo"
    top = files[0].split("/")[0].split("\\")[0]
    return top or "repo"


def infer_type(files: List[str]) -> str:
    joined = " ".join(files).lower()
    if any(x in joined for x in ["test", "spec"]):
        return "test"
    if any(x.endswith(ext) for x in files for ext in [".md", ".txt"]):
        return "docs"
    if len(files) <= 2:
        return "chore"
    return "feat"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python prepare_commit_msg.py <commit_msg_file>")

    msg_file = Path(sys.argv[1])
    current = msg_file.read_text(encoding="utf-8", errors="replace") if msg_file.exists() else ""
    first = current.strip().splitlines()[0] if current.strip() else ""
    if first and not first.startswith("#"):
        return

    key = get_current_scrum_key()
    files = staged_files()
    ctype = infer_type(files)
    scope = infer_scope(files)
    count = len(files)
    subject = f"{ctype}({scope}): update {count} file{'s' if count != 1 else ''}"
    if key:
        subject = f"{key}: {ctype}({scope}): update {count} file{'s' if count != 1 else ''}"

    template = subject + "\n\n"
    if files:
        template += "Changed:\n" + "\n".join(f"- {f}" for f in files[:20]) + "\n"
        if count > 20:
            template += f"- ... ({count - 20} more)\n"

    if key:
        template += f"\n# 현재 SCRUM 키: {key} (.current-scrum-key)\n"
    else:
        template += "\n# SCRUM 키 없음. echo 'SCRUM-XX' > .current-scrum-key 로 설정 가능\n"

    msg_file.write_text(template, encoding="utf-8")


if __name__ == "__main__":
    main()
