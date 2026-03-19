# Jira Workflow Rules

## 핵심 원칙 (2026-03-19 변경)

```
브랜치 = 기능(Feature) 단위  →  SCRUM 키 브랜치명에 넣지 않는다
커밋   = Jira 이슈(SCRUM) 단위  →  커밋 1개 = SCRUM 이슈 1개
```

## 브랜치 명명

```
feature/{기능-슬러그}     # 예: feature/kpi-dashboard
fix/{버그-슬러그}         # 예: fix/event-store-null-crash
refactor/{대상-슬러그}    # 예: refactor/backend-route-split
chore/{작업-슬러그}       # 예: chore/update-eslint-config
hotfix/{이슈-슬러그}      # 예: hotfix/login-token-expired
```

- 슬러그: 영문 소문자 + 하이픈, 최대 40자
- **SCRUM-XX 키를 브랜치명에 포함하지 않는다** (커밋 메시지에만 포함)
- 하나의 브랜치에 여러 SCRUM 이슈가 들어갈 수 있음

## 커밋 메시지

```
{JIRA_KEY}: {동사 원형으로 시작하는 요약 (영문, 50자 이내)}
```

예:
```
SCRUM-38: Add KPI chart skeleton component
SCRUM-39: Connect sprint data via useQuery hook
SCRUM-40: Fix null guard on empty sprint response
SCRUM-41: WIP KPI page sub-component refactor
```

규칙:
- **Jira 키는 모든 커밋에 반드시 포함**
- 동사: Add / Fix / Update / Refactor / Remove / Move / Rename
- 커밋 1개당 Jira 이슈 1개 (1:1 매핑 유지)

## 현재 작업 SCRUM 키 관리

```bash
# 작업 시작 시 현재 이슈 키 기록
echo "SCRUM-38" > .current-scrum-key

# 다음 이슈로 전환 시
echo "SCRUM-39" > .current-scrum-key

# 완료 후 삭제
rm .current-scrum-key
```

- `prepare_commit_msg.py` hook이 이 파일을 읽어 커밋 메시지 자동 prefix
- `.current-scrum-key`는 `.gitignore`에 추가

## PR 규칙

- 제목: `feature: {기능 설명} (SCRUM-XX, XX, XX)`
- body에 연관 이슈 전체 목록 명시
- PR 생성 시 Jira 상태 → In Review 전환

## Jira 상태 전환

| 이벤트 | Jira 상태 |
|--------|-----------|
| 브랜치 생성 + 작업 시작 | In Progress |
| PR 오픈 | In Review |
| PR Merge + 배포 | Done |

## 자동화 스크립트 (`automation/jira/`)

- **이슈 생성 + 브랜치**: `python automation/jira/dev_workflow.py create-issue`
  - 브랜치 슬러그 입력 시 SCRUM 키 제외하고 기능명만 입력
- **MR 생성**: `python automation/jira/dev_workflow.py create-mr`
- **hook 설치** (최초 1회): `python automation/jira/install_git_hook.py --repo .`
- **일일 동기화**: `python automation/jira/jira_daily_sync.py`

## 작업 완료 시 필수 체크

- [ ] 모든 커밋에 Jira 키 포함 확인 (`git log --oneline`)
- [ ] 커밋 1개 = 이슈 1개 확인
- [ ] PR body에 연관 이슈 전체 나열
- [ ] Jira 이슈 상태 In Review 전환
- [ ] `.current-scrum-key` 삭제
