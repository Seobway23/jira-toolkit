# jira-toolkit

> Jira + Git + GitHub Actions 자동화 툴킷.
> 어느 프로젝트든 한 줄로 주입 가능.

---

## 이게 뭐임?

커밋할 때마다 Jira를 손으로 업데이트하기 귀찮은 사람들을 위한 툴킷.

```
PR 오픈  →  Jira 자동으로 In Review
PR 머지  →  Jira 자동으로 Done
커밋     →  메시지에 SCRUM-XX 자동 prefix
```

**수동 모드**와 **AI 모드(Claude Code)** 둘 다 지원.

---

## 설치 (새 프로젝트에 주입)

```bash
# 1. 이 레포 클론
git clone https://github.com/Seobway23/jira-toolkit
cd jira-toolkit

# 2. 대상 프로젝트에 주입 (dry-run 먼저)
python automation/jira/setup_project.py --target /path/to/your-project --dry-run

# 3. 실제 주입
python automation/jira/setup_project.py --target /path/to/your-project
```

주입되는 것:
```
your-project/
  automation/jira/        ← Python 자동화 스크립트
  .github/workflows/      ← GitHub Actions (PR → Jira 자동 전환)
  .claude/rules/          ← AI 모드용 규칙
  .env.example            ← 환경변수 템플릿
```

---

## 환경변수 설정

```bash
cp automation/jira/env.example .env
# .env 열어서 값 채우기
```

```env
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_KEY=your_api_key_here
JIRA_PROJECT_KEY=SCRUM
GITHUB_TOKEN=ghp_xxxx
```

Jira API 토큰 발급:
```
https://id.atlassian.com/manage-profile/security/api-tokens
```

---

## GitHub Actions 설정

PR 머지 시 Jira 자동 Done 처리를 위해 GitHub Secrets 등록 필요:

```
GitHub 저장소 → Settings → Secrets and variables → Actions
```

| Secret | 값 |
|--------|-----|
| `JIRA_BASE_URL` | `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | `you@company.com` |
| `JIRA_API_KEY` | Jira API 토큰 |

---

## 수동 모드

```bash
# git hook 설치 (커밋 메시지 자동 prefix)
python automation/jira/install_git_hook.py --repo .

# 작업 시작
git checkout -b feature/my-feature
echo "SCRUM-38" > .current-scrum-key

# 커밋 (SCRUM-38: 자동으로 붙음)
git add .
git commit -m "SCRUM-38: Add my feature"

# PR 생성 + Jira In Review 자동 전환
git push origin feature/my-feature
python automation/jira/dev_workflow.py create-mr

# PR 머지 후 → GitHub Actions가 Jira Done 자동 처리
```

---

## AI 모드 (Claude Code)

```bash
npm install -g @anthropic-ai/claude-code
claude  # 프로젝트 루트에서 실행
```

이렇게만 말하면 됨:

| 상황 | 말하는 것 |
|------|----------|
| 작업 시작 | `"SCRUM-38 브랜치 만들어줘"` |
| 구현 | `"SCRUM-38: 로그인 API 구현해줘"` |
| PR | `"PR 만들어줘"` |
| 완료 | `"SCRUM-38 Done 처리해줘"` |

`.claude/rules/`가 주입되면 Claude가 Jira 전략 자동 인식.

---

## 브랜치 전략

```
브랜치 = 기능 단위   →  feature/my-feature
커밋   = SCRUM 단위  →  SCRUM-38: Add login API
```

자세한 내용: [docs/GIT_BRANCH_STRATEGY.md](docs/GIT_BRANCH_STRATEGY.md)

---

## 파일 구조

```
jira-toolkit/
  automation/jira/
    dev_workflow.py           # Jira 이슈 생성 + PR 생성 (GitHub/GitLab 자동 감지)
    pr_event_sync.py          # PR 이벤트 → Jira 상태 전환
    ci_pr_event_entrypoint.py # GitHub/GitLab CI 래퍼
    prepare_commit_msg.py     # 커밋 메시지 자동 prefix hook
    install_git_hook.py       # hook 설치
    setup_project.py          # 새 프로젝트에 주입하는 스크립트
    jira_sprint_bootstrap.py  # 스프린트/이슈 일괄 생성
    jira_daily_sync.py        # 일일 동기화
    test_jira_env.py          # 환경변수 검증
    env.example               # 환경변수 템플릿
    requirements.txt
  .github/workflows/
    jira_done_on_merge.yml    # PR 오픈→In Review, 머지→Done
  .claude/rules/
    jira-workflow.md          # AI 모드용 Jira 규칙
  docs/
    GIT_BRANCH_STRATEGY.md
```

---

## License

MIT
