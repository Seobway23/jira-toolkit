# dev_workflow.py 사용 가이드

Jira 이슈 생성 → Git 브랜치 → GitLab MR까지 자동화하는 스크립트.

---

## 사전 준비

`.env` 파일 위치: `C:/Users/USER/Desktop/hellomd/.env`

현재 설정된 값:
```
JIRA_EMAIL=seobway24@gmail.com
JIRA_API_KEY=...
JIRA_BASE_URL=https://seobway24.atlassian.net/
JIRA_PROJECT_KEY=SCRUM
GITLAB_TOKEN=glpat-...
GITLAB_PROJECT_MANAGEMENT_ID=ds-it-team/project-management
```

---

## 명령어 3가지

```bash
# 위치 이동 (선택)
cd C:/Users/USER/Desktop/hellomd/automation/jira

# 1. Jira 이슈만 생성 + 브랜치 자동 생성
python dev_workflow.py create-issue

# 2. 현재 브랜치로 GitLab MR만 생성
python dev_workflow.py create-mr

# 3. 이슈 생성 + 브랜치 + MR 한번에
python dev_workflow.py full
```

---

## 전체 워크플로우 예시

### Step 1 — Jira 이슈 생성 + 브랜치

```bash
python dev_workflow.py create-issue
```

프롬프트 입력 예시:
```
이슈 제목: Admin 부서/직책 관리 페이지 구현
설명: CRU 기능, 반응형 레이아웃 포함 (Enter 스킵 가능)
타입 [Story/Bug/Task]: Story
스토리 포인트: 5
브랜치 슬러그: admin-dept-position-management
base 브랜치: dev
```

결과:
```
✅ 이슈 생성: SCRUM-39 — https://seobway24.atlassian.net/browse/SCRUM-39
✅ 브랜치 생성: feature/SCRUM-39-admin-dept-position-management
   Jira 상태: 진행 중으로 자동 전환
```

자동으로 하는 것:
- Jira 이슈 생성 (Story Points, Active Sprint 연동)
- 담당자 자동 배정 (seobway)
- Jira 상태 → **진행 중**
- `feature/SCRUM-39-...` 브랜치 생성 (dev 기반)

---

### Step 2 — 코드 작업

```bash
# 코드 수정 후
git add .
git commit -m "SCRUM-39: Add admin department management page"
git push -u origin feature/SCRUM-39-admin-dept-position-management
```

> 커밋 메시지 규칙: `SCRUM-{N}: {동사} {내용}` (50자 이내)
> 동사: Add / Fix / Update / Refactor / Remove

---

### Step 3 — GitLab MR 생성

```bash
python dev_workflow.py create-mr
```

프롬프트 입력 예시:
```
target 브랜치: dev
MR 제목: SCRUM-39: Admin 부서/직책 관리 페이지 구현
설명: (Enter 스킵하면 자동 생성)
```

결과:
```
✅ MR 생성 완료: https://gitlab.com/ds-it-team/project-management/-/merge_requests/5
✅ Jira 상태 → 검토 중
```

---

## 이슈 타입별 브랜치 prefix

| Jira 타입 | 브랜치 prefix |
|-----------|--------------|
| Story     | `feature/`   |
| Bug       | `fix/`       |
| Task      | `chore/`     |
| Subtask   | `chore/`     |

---

## Jira 상태 자동 전환 요약

| 시점 | Jira 상태 |
|------|-----------|
| `create-issue` 실행 시 | **진행 중** |
| `create-mr` 실행 시 | **검토 중** |
| Merge 후 (수동) | Done |

---

## 자주 쓰는 패턴

### 버그 수정

```bash
python dev_workflow.py create-issue
# 타입: Bug → 브랜치가 fix/SCRUM-N-... 으로 생성됨
```

### MR만 빠르게

```bash
# 이미 브랜치에서 작업 중일 때
python dev_workflow.py create-mr
```

### 새 기능 처음부터 끝까지

```bash
python dev_workflow.py full
# 이슈 정보 입력 → 코드 작업 → Enter → MR 자동 생성
```

---

## 스크립트 위치

```
C:/Users/USER/Desktop/hellomd/
└── automation/
    └── jira/
        ├── dev_workflow.py   ← 스크립트
        └── DEV_WORKFLOW_GUIDE.md   ← 지금 이 파일
```
