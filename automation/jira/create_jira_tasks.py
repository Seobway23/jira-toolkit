"""
Jira 이슈 생성 스크립트.
front/ops-portal/.env 의 JIRA_* 변수를 읽어 Jira Cloud API로 Task를 생성합니다.

사용법:
  python automation/jira/create_jira_tasks.py
  python automation/jira/create_jira_tasks.py --env "C:/path/to/.env"
  python automation/jira/create_jira_tasks.py --dry-run
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen


def _strip_quotes(text: str) -> str:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_key = key.strip().strip('"').strip("'")
        if not env_key or env_key in os.environ:
            continue
        os.environ[env_key] = _strip_quotes(value)


def preload_env(env_path: Optional[Path] = None) -> None:
    if env_path:
        load_env_file(env_path)
        return
    # 기본: front/ops-portal/.env (이 스크립트 기준 hellomd/automation/jira -> hellomd/front/ops-portal/.env)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    default_env = repo_root / "front" / "ops-portal" / ".env"
    for p in [default_env, Path.cwd() / ".env", Path.cwd() / "front" / "ops-portal" / ".env"]:
        if p.exists():
            load_env_file(p)
            return


def jira_auth_header() -> str:
    email = os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USER_EMAIL") or ""
    token = os.getenv("JIRA_API_KEY") or os.getenv("JIRA_API_TOKEN") or ""
    raw = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("utf-8")


def adf_doc(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text or ""}]}],
    }


def jira_create_issue(
    project_key: str,
    issue_type: str,
    summary: str,
    description: str,
    dry_run: bool = False,
) -> dict:
    base = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("JIRA_BASE_URL missing in .env")
    payload = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }
    }
    if description:
        payload["fields"]["description"] = adf_doc(description)

    if dry_run:
        print(f"[DRY-RUN] POST {base}/rest/api/3/issue")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return {"key": f"{project_key}-DRY"}

    url = f"{base}/rest/api/3/issue"
    req = Request(url, method="POST")
    req.add_header("Authorization", jira_auth_header())
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/json")
    body = json.dumps(payload).encode("utf-8")
    with urlopen(req, data=body, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=".env 기반으로 Jira Task 생성")
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help=".env 파일 경로 (기본: front/ops-portal/.env)",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Jira 프로젝트 키 (기본: .env의 JIRA_PROJECT_KEY)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 생성 없이 요청 payload만 출력",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=2,
        help="생성할 Task 개수 (기본 2)",
    )
    args = parser.parse_args()

    preload_env(args.env)
    project_key = args.project or os.getenv("JIRA_PROJECT_KEY") or "SCRUM"

    if not args.dry_run:
        if not os.getenv("JIRA_EMAIL") and not os.getenv("JIRA_USER_EMAIL"):
            print("Error: JIRA_EMAIL or JIRA_USER_EMAIL missing in .env", file=sys.stderr)
            return 1
        if not os.getenv("JIRA_API_KEY") and not os.getenv("JIRA_API_TOKEN"):
            print("Error: JIRA_API_KEY or JIRA_API_TOKEN missing in .env", file=sys.stderr)
            return 1

    base_url = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
    created = []
    tasks = [
        ("Task", "PMS API 연동 검증용 Task 1", "create_jira_tasks.py 스크립트로 생성된 테스트 이슈입니다."),
        ("Task", "PMS API 연동 검증용 Task 2", "Jira REST API 이슈 생성 확인용입니다."),
    ]
    for i, (issue_type, summary, description) in enumerate(tasks):
        if i >= args.count:
            break
        try:
            out = jira_create_issue(project_key, issue_type, summary, description, dry_run=args.dry_run)
            key = out.get("key", "")
            created.append(key)
            if not args.dry_run:
                print(f"Created: {key} - {summary}")
        except Exception as e:
            print(f"Failed: {summary} - {e}", file=sys.stderr)
            return 1

    if args.dry_run:
        print(f"[DRY-RUN] Would create {len(created)} issue(s).")
        return 0

    if created:
        print()
        print("--- Created issues ---")
        for key in created:
            print(f"  {key}: {base_url}/browse/{key}")
        print()
        print("Check the links above in Jira.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
