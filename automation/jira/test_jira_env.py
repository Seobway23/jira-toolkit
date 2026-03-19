"""
루트 또는 지정한 .env 로드 후 Jira API 연결 가능 여부만 검사합니다.
이슈 생성/수정 없이 GET /rest/api/3/myself 로 인증만 확인합니다.

사용법:
  python automation/jira/test_jira_env.py
  python automation/jira/test_jira_env.py --env "C:/Users/USER/Desktop/hellomd/.env"
"""
import argparse
import base64
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
        p = Path(env_path).resolve()
        if not p.is_absolute():
            p = Path.cwd() / p
        load_env_file(p)
        return
    repo_root = Path(__file__).resolve().parent.parent.parent
    for p in [Path.cwd() / ".env", repo_root / ".env", repo_root / "front" / "ops-portal" / ".env"]:
        if p.exists():
            load_env_file(p)
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Jira API with .env")
    parser.add_argument("--env", type=Path, default=None, help=".env file path (default: root or cwd .env)")
    args = parser.parse_args()

    preload_env(args.env)

    base = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
    email = os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USER_EMAIL") or ""
    token = os.getenv("JIRA_API_KEY") or os.getenv("JIRA_API_TOKEN") or ""

    if not base:
        print("Error: JIRA_BASE_URL missing in .env", file=sys.stderr)
        return 1
    if not email or not token:
        print("Error: JIRA_EMAIL and JIRA_API_KEY (or JIRA_API_TOKEN) required in .env", file=sys.stderr)
        return 1

    auth = "Basic " + base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("utf-8")
    url = f"{base}/rest/api/3/myself"
    req = Request(url, method="GET")
    req.add_header("Authorization", auth)
    req.add_header("Accept", "application/json")

    try:
        with urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            import json
            me = json.loads(data)
            name = me.get("displayName") or me.get("emailAddress") or "?"
            print(f"OK: Jira API connection successful (user: {name})")
            return 0
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
