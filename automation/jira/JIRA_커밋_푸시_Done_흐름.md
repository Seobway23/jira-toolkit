# Jira 연동: 커밋 / 푸시 / Done 흐름 정리

## 1. 지금 구조에서 “무엇이 언제” 실행되는지


| 시점              | 실행되는 것                                           | Jira에 하는 일                                   |
| --------------- | ------------------------------------------------ | -------------------------------------------- |
| **Commit** (로컬) | `prepare-commit-msg` 훅 → `prepare_commit_msg.py` | **없음.** 메시지에 Jira 키만 붙임.                     |
| **Push**        | Git 원격에 올리는 것만 있음                                | **없음.** (별도 CI/웹훅 없으면 Jira API 호출 안 함)       |
| **PR 생성/수정**    | (CI 붙이면) `pr_event_sync.py`                      | Jira 이슈에 **코멘트**만 추가 (Done 전환 안 함)           |
| **PR Merge**    | (CI 붙이면) `pr_event_sync.py --event merged`       | PR 제목에서 Jira 키 찾아서 해당 이슈 **Done으로 전환** + 코멘트 |


즉,

- **Commit** → 로컬에서 커밋 메시지 형태만 바뀜 (예: `SCRUM-123 feat(...): ...`).  
이 시점에는 Jira API 호출이 **전혀 없음**.
- **Push만** 해서는 **아무 자동 실행도 없음**.  
“Push 하면 뭔가 실행돼서 Jira가 Done 된다”는 건 **현재 기본 설정만으로는 아님**.
- **Jira 이슈가 Done으로 바뀌는 시점**은 **PR이 merge될 때**이고, 그때 **CI에서** `pr_event_sync.py`를 `--event merged`로 실행해줘야 함.

---

## 2. “Commit → Push → Jira Done” 이 되려면

**Push만으로는 Done 처리 안 됨.**  
Jira를 Done으로 만들려면 아래 둘 중 하나가 필요함.

### 방법 A: PR Merge 시 Done (권장)

1. **브랜치/커밋 규칙**
  - 브랜치: `feature/SCRUM-123-...` 처럼 이름에 Jira 키 포함  
  - 커밋: `SCRUM-123 feat: ...` (prepare-commit-msg 훅이 자동으로 붙여 줌)  
  - **PR 제목에도 Jira 키 포함**: 예) `SCRUM-123 Implement ...`
2. **CI에서 PR이 merge될 때 스크립트 실행**
  - GitHub 사용 시:  
    - 저장소에 `.github/workflows/` 아래에 “PR closed + merged” 일 때  
    `automation/jira/ci_pr_event_entrypoint.py` 를 호출하는 워크플로 추가.
  - 이 워크플로가  
    - PR 제목에서 `SCRUM-123` 같은 키를 찾고  
    - `pr_event_sync.py --event merged --title "PR 제목" --url "PR URL"` 를 실행
  - `pr_event_sync.py` 가  
    - 해당 Jira 이슈에 코멘트 추가  
    - `**event == "merged"` 일 때 `transition_done()` 호출** → Jira에서 **Done**으로 전환
3. **실제 흐름**
  - Commit (로컬) → 메시지에 Jira 키 붙음  
  - Push → 원격 브랜치에 반영  
  - PR 생성 (제목에 Jira 키 포함)  
  - PR Merge → CI 실행 → `pr_event_sync.py --event merged` → **Jira Done**

### 방법 B: Push만으로 Done 하고 싶을 때

- “Push만 하면 Done”으로 만들려면  
  - **main/master에 push될 때** 동작하는 GitHub Actions(또는 GitLab CI)를 하나 더 만든 뒤  
  - “마지막 커밋 메시지”에서 Jira 키를 파싱해서  
  - 같은 `transition_done()` 로직을 호출하는 식으로 구현해야 함.
- 보통은 **PR Merge = 작업 완료**로 보기 때문에 **방법 A(PR Merge 시 Done)** 를 쓰는 게 일반적임.

---

## 3. 정리: 질문에 대한 답

- **Commit 하면 어떤 형태가 주어지나?**  
→ 로컬에서 **커밋 메시지**가 `SCRUM-123 feat(scope): ...` 형태로 채워짐 (prepare-commit-msg 훅).  
그 외 형태의 “자동 실행”은 없고, **Jira API는 호출되지 않음.**
- **Push 하면 어떤 형태가 주어지나?**  
→ **Push 자체만** 있음.  
GitHub/GitLab이 push를 받는 것까지가 전부이고,  
**별도로 설정한 CI/웹훅이 없으면** Jira 쪽으로는 아무 일도 안 일어남.
- **“Commit 하고 Push 하면 Jira가 Done 된다”는 말이 맞나?**  
→ **기본만 두면 아님.**  
**PR을 만들고, 그 PR을 merge할 때** CI에서 `pr_event_sync.py --event merged` 가 돌아가야 Jira가 Done으로 바뀜.  
그래서 “Commit → Push → **PR 생성 → PR Merge**” 까지 가야 Jira가 끝나는 흐름이라고 보면 됨.
- **그렇게 Jira가 끝나게 할 수 있나?**  
→ **가능함.**  
PR Merge 시 `pr_event_sync.py`를 실행하는 **GitHub Actions(또는 GitLab CI)를 저장소에 추가**하면 됨.  
이 레포에는 이미  
  - `automation/jira/pr_event_sync.py` (Done 전환 로직)  
  - `automation/jira/ci_pr_event_entrypoint.py` (CI에서 부르는 진입점)  
  - `automation/jira/github_actions_jira_done.sample.yml` (샘플 워크플로)  
  가 있으므로, 이 샘플을 복사해서 `.github/workflows/` 에 넣고,  
  **GitHub Secrets**에 `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_KEY` 를 넣으면 PR Merge 시 Jira가 Done으로 전환됨.

---

## 4. PR Merge 시 Jira Done 쓰려면 할 일 체크리스트

1. **PR 제목에 Jira 키 넣기**
  예: `SCRUM-123 Add login API`
2. **hellomd 루트에 GitHub Actions 워크플로 추가**
  - 파일: `.github/workflows/jira_done_on_merge.yml`  
  - 내용: `automation/jira/github_actions_jira_done.sample.yml` 참고해서  
    - trigger: `pull_request` types `closed`  
    - job에서 `ci_pr_event_entrypoint.py --source github` 실행  
    - env에 `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_KEY` (Secrets에서 주입)
3. **GitHub 저장소 Secrets 등록**
  - `JIRA_BASE_URL`  
  - `JIRA_EMAIL`  
  - `JIRA_API_KEY`
4. **실제로 PR Merge**
  - Merge 되면 워크플로가 돌면서 PR 제목에서 키 추출 → 해당 Jira 이슈 Done 전환.

이렇게 하면 “Commit → Push → PR Merge” 시 해당 Jira 이슈가 자동으로 Done으로 끝나게 할 수 있음.