# Git 브랜치 & Jira 연동 전략 가이드

> 최종 수정: 2026-03-19
> 기존 "브랜치 단위 SCRUM" → **"커밋 단위 SCRUM"** 전략으로 변경

---

## 핵심 원칙

```
브랜치 = 기능(Feature) 단위
커밋   = Jira 이슈(SCRUM) 단위
```

### 왜 바꾸는가?

**기존 방식 (문제)**
```
branch: feature/SCRUM-38-kpi-dashboard
  ├── commit: SCRUM-38: Add KPI chart component
  ├── commit: SCRUM-38: Fix null data
  ├── commit: SCRUM-38: Update color scheme
  ├── commit: SCRUM-38: Refactor query hook
  └── commit: SCRUM-38: Add loading state
```
→ 커밋이 5개인데 Jira 이슈는 1개. "어떤 커밋이 어떤 작업인지" 매핑 불가.
→ SCRUM-39, SCRUM-40 이 같은 기능에 붙는다면 브랜치를 또 새로 파야 함.

**새 방식 (해결)**
```
branch: feature/kpi-dashboard
  ├── commit: SCRUM-38: Add KPI chart component skeleton
  ├── commit: SCRUM-39: Connect real data via TanStack Query
  ├── commit: SCRUM-40: Fix null guard on empty sprint data
  └── commit: SCRUM-41: Add loading/error state UI
```
→ 커밋 1개 = Jira 이슈 1개. 1:1 매핑.
→ 관련 여러 이슈가 하나의 기능 브랜치에 모임. PR 1개로 리뷰 가능.

---

## 브랜치 명명 규칙

```
{type}/{기능-슬러그}
```

| type      | 사용 시점 | 예시 |
|-----------|----------|------|
| `feature` | 새 기능 구현 | `feature/kpi-dashboard` |
| `fix`     | 버그 수정 | `fix/event-store-null-crash` |
| `refactor`| 리팩토링 (기능 변화 없음) | `refactor/backend-route-split` |
| `chore`   | 설정, 의존성, 문서 | `chore/update-eslint-config` |
| `hotfix`  | 프로덕션 긴급 패치 | `hotfix/login-token-expired` |

**규칙:**
- 슬러그: 영문 소문자 + 하이픈, 최대 40자
- **SCRUM 키 브랜치명에 넣지 않는다** ← 핵심 변경점
- 브랜치 하나가 여러 SCRUM 이슈를 커버할 수 있다

---

## 커밋 메시지 규칙

```
{JIRA_KEY}: {동사} {내용} (50자 이내)
```

| 동사 | 사용 시점 |
|------|----------|
| `Add` | 새 파일/기능 추가 |
| `Fix` | 버그 수정 |
| `Update` | 기존 기능 수정/개선 |
| `Refactor` | 리팩토링 |
| `Remove` | 코드/파일 삭제 |
| `Move` | 파일/코드 이동 |

**예시:**
```
SCRUM-38: Add KPI chart skeleton component
SCRUM-39: Connect sprint data via useQuery hook
SCRUM-40: Fix null guard on empty sprint response
SCRUM-41: Refactor KPI page into sub-components
```

**WIP 커밋도 키 포함:**
```
SCRUM-38: WIP KPI chart layout
```

---

## 전체 워크플로우 (수동 방법)

### Step 1 — 작업 시작 전 준비

```bash
# 1. main 최신화
git checkout main
git pull origin main

# 2. 기능 브랜치 생성 (SCRUM 키 없이 기능명으로)
git checkout -b feature/kpi-dashboard

# 3. 현재 작업 중인 SCRUM 키 기록 (자동 커밋 prefix용)
echo "SCRUM-38" > .current-scrum-key
```

> `.current-scrum-key` 파일은 `.gitignore`에 추가해두면 됨
> `prepare_commit_msg.py` hook이 이 파일을 읽어 커밋 메시지 자동 prefix

### Step 2 — 코드 작업 + 커밋

**SCRUM 이슈 하나당 커밋 하나:**

```bash
# SCRUM-38 작업 완료 후
git add src/components/KPIChart.tsx
git commit -m "SCRUM-38: Add KPI chart skeleton component"

# SCRUM-39로 이동 (키 파일 업데이트)
echo "SCRUM-39" > .current-scrum-key

# SCRUM-39 작업 완료 후
git add src/hooks/useKPIData.ts
git commit -m "SCRUM-39: Connect sprint data via useQuery hook"
```

### Step 3 — Push + PR 생성

```bash
# 브랜치 push
git push -u origin feature/kpi-dashboard

# PR 제목: 브랜치의 기능을 설명 (SCRUM 키 여러 개 포함 가능)
# 예: "feature: KPI dashboard with real data (SCRUM-38, 39, 40, 41)"
```

PR body에 연관 이슈 목록 명시:
```markdown
## Related Issues
- SCRUM-38: KPI chart skeleton
- SCRUM-39: Real data connection
- SCRUM-40: Null guard fix
- SCRUM-41: Component refactor
```

### Step 4 — 완료 후 정리

```bash
# .current-scrum-key 삭제 (또는 다음 이슈로 업데이트)
rm .current-scrum-key

# Jira 이슈 상태 수동 전환: In Review → Done
```

---

## 시뮬레이션: 현재 브랜치 분석

현재 브랜치: `feature/SCRUM-2-dev-kpi-automation-phase2`

**기존 방식:**
```
feature/SCRUM-2-dev-kpi-automation-phase2
  └── SCRUM-2: Add Phase 1/2 automation pipeline and DEV KPI real data
```

**새 방식으로 이름 변경 시:**
```
feature/dev-kpi-automation-phase2
  ├── SCRUM-2: Add Phase 1 sprint bootstrap automation pipeline
  ├── SCRUM-3: Add Phase 2 KPI real data connection
  └── SCRUM-4: Update DEV workflow guide and git hooks
```

→ SCRUM-2 커밋 1개가 3가지 작업을 묶어버린 게 현재 문제.
→ 앞으로는 작업 단위로 쪼개서 커밋 1개 = SCRUM 1개 유지.

---

## 브랜치 생명주기

```
main ──────────────────────────────────────────────────► main
       │                                         ▲
       └── feature/kpi-dashboard ────────────────┘
             │
             ├── SCRUM-38: Add chart skeleton
             ├── SCRUM-39: Connect real data
             └── SCRUM-40: Fix null guard
                  └── [PR merged] → Jira: Done
```

---

## 자동화 스크립트 사용법 (새 전략 기준)

```bash
# dev_workflow.py - 이슈 생성 + 브랜치 (슬러그에 SCRUM 키 제외)
python automation/jira/dev_workflow.py create-issue
# 브랜치 슬러그 입력 시: kpi-dashboard (SCRUM-38 입력하지 말 것)

# commit hook 설치 (한 번만)
python automation/jira/install_git_hook.py --repo .

# 현재 SCRUM 키 설정
echo "SCRUM-38" > .current-scrum-key
```

---

## 플러그인 다른 프로젝트에 적용하는 법

### 방법 A: 글로벌 rules 활용 (추천 - 이미 설정됨)

`~/.claude/rules/` 폴더의 파일들은 **모든 프로젝트에 자동 적용**됨.
현재 이미 `~/.claude/rules/jira-workflow.md`가 설정되어 있음.

```
~/.claude/
  rules/
    jira-workflow.md  ← 전체 프로젝트 공통 Jira 규칙
  settings.json       ← 전체 프로젝트 공통 권한
```

### 방법 B: 프로젝트별 CLAUDE.md에 공통 규칙 import

새 프로젝트의 CLAUDE.md에 아래 추가:
```markdown
@~/.claude/rules/jira-workflow.md
```

### 방법 C: 스크립트로 자동 복사

```bash
# 새 프로젝트에 automation 폴더 통째로 복사
cp -r /path/to/hellomd/automation/ /path/to/new-project/automation/

# git hook 재설치
python automation/jira/install_git_hook.py --repo /path/to/new-project
```

### 방법 D: AI한테 전달하는 방법

새 프로젝트에서 Claude에게:
```
이 프로젝트에 ~/Desktop/hellomd/.claude/rules/ 폴더의 규칙들을 적용해줘.
CLAUDE.md 만들고 automation/jira/ 스크립트도 복사해줘.
```

→ AI가 CLAUDE.md 보고 규칙 자동 인식. 별도 플러그인 설치 불필요.

---

## .gitignore 추가 항목

```gitignore
# 로컬 SCRUM 키 추적 파일
.current-scrum-key
```

---

## 체크리스트

### 작업 시작 시
- [ ] `git checkout main && git pull`
- [ ] `git checkout -b feature/{기능명}` (SCRUM 키 없이)
- [ ] `echo "SCRUM-XX" > .current-scrum-key`
- [ ] Jira 이슈 상태 → In Progress

### 커밋 시
- [ ] 커밋 1개 = Jira 이슈 1개
- [ ] 메시지 형식: `SCRUM-XX: {동사} {내용}`
- [ ] `.current-scrum-key` 다음 이슈로 업데이트

### PR 생성 시
- [ ] PR body에 연관 SCRUM 이슈 전체 나열
- [ ] Jira 이슈 상태 → In Review
- [ ] `python automation/jira/dev_workflow.py create-mr`

### 완료 시
- [ ] PR merge
- [ ] Jira 이슈 상태 → Done
- [ ] `rm .current-scrum-key`
