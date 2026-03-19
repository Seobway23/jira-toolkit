# Jira 브랜치·커밋 설정 가이드 (prepare-commit-msg 훅)

## 1. 현재 훅이 하는 일

`prepare-commit-msg` 훅은 **커밋 메시지 파일이 비어 있거나 기본 템플릿(첫 줄이 `#` 주석)일 때만** 동작합니다.

- **스크립트**: `automation/jira/prepare_commit_msg.py`
- **호출**: Git이 `git commit` 시 메시지 파일 경로를 `$1`로 넘김  
  예: `python "C:/Users/USER/Desktop/hellomd/automation/jira/prepare_commit_msg.py" "$1"`

동작 요약:

1. 현재 브랜치 이름에서 Jira 이슈 키 추출 (정규식: `[A-Z]+-\d+`, 예: `SCRUM-123`)
2. 스테이징된 파일 목록으로 타입/스코프 추론 (feat, docs, test, chore 등)
3. **이슈 키가 있으면** 커밋 제목 앞에 `{키} ` 붙임  
   예: `SCRUM-123 feat(front): update 3 files`
4. 변경 파일 목록을 본문에 추가

---

## 2. Jira 브랜치 어떻게 잡을지

**브랜치 이름 안에 Jira 이슈 키가 들어가야** 훅이 인식합니다.

- 패턴: **대문자영문+하이픈+숫자** → `SCRUM-42`, `HELLO-123`, `PROJ-1` 등

### 권장 브랜치 이름 예

| 형식 | 예시 |
|------|------|
| `feature/키-짧은설명` | `feature/SCRUM-123-add-login` |
| `fix/키-설명` | `fix/SCRUM-456-fix-crash` |
| `키/설명` | `SCRUM-789/refactor-api` |
| `키` 만 있어도 됨 | `SCRUM-42` |

**주의**: 브랜치 이름에 `SCRUM-123` 같은 키가 **한 번이라도** 포함되면 됩니다.  
예: `feature/login-SCRUM-123` → `SCRUM-123` 추출됨.

### 잘 안 되는 예

- `feature/login` → 키 없음 → 커밋 제목에 Jira 키 안 붙음
- `scrum-123` → 소문자만 있음 → 정규식 `[A-Z]+-\d+` 에 안 걸림 (대문자 필요)

---

## 3. 커밋은 어떻게 해야 하는지

### A. 훅이 메시지를 채우게 하려면 (권장)

1. 브랜치를 위 규칙대로 만든다 (예: `feature/SCRUM-123-add-x`)
2. `git add` 로 스테이징
3. **`-m` 없이** 커밋:
   ```bash
   git commit
   ```
4. 에디터가 열리면, 훅이 이미 채운 메시지(예: `SCRUM-123 feat(front): update 2 files`)가 있음. 그대로 저장 후 닫으면 됨.

이때만 훅이 메시지 파일을 **덮어씁니다**. (첫 줄이 비어 있거나 `#`로 시작할 때)

### B. 직접 메시지를 쓰는 경우

- `git commit -m "내 메시지"` 처럼 **이미 메시지를 주면** 훅은 아무것도 안 함 (첫 줄이 `#`가 아니므로).
- Jira에 커밋이 연결되게 하려면, 메시지 **맨 앞에** 이슈 키를 넣는 게 좋습니다.  
  예: `SCRUM-123 fix: 로그인 버그 수정`

### C. 요약

| 하고 싶은 것 | 브랜치 | 커밋 방법 |
|-------------|--------|-----------|
| 훅이 제목까지 자동 생성 | `feature/SCRUM-123-...` 처럼 키 포함 | `git commit` (에디터에서 확인) |
| 직접 메시지 작성 | 상관없음 | `git commit -m "SCRUM-123 ..."` 처럼 맨 앞에 키 |

---

## 4. 훅 설정 확인·재설치

### 훅이 어디에 있어야 하는지

- **경로**: 해당 Git 저장소 안 `.githooks/prepare-commit-msg`
- **설정**: `git config core.hooksPath .githooks` 로 훅 디렉터리를 `.githooks`로 지정

현재 웹훅에 들어간 내용 예시는 다음과 같습니다.

```sh
#!/usr/bin/env sh
set -e
python "C:/Users/USER/Desktop/hellomd/automation/jira/prepare_commit_msg.py" "$1"
```

### 한 번에 설치/재설치

hellomd 루트에서:

```bash
python automation/jira/install_git_hook.py --repo "C:/Users/USER/Desktop/hellomd"
```

다른 저장소에 쓸 때:

```bash
python automation/jira/install_git_hook.py --repo "C:/경로/저장소"
```

이렇게 하면 `.githooks/prepare-commit-msg` 가 생성되고 `core.hooksPath` 가 `.githooks` 로 설정됩니다.

### 동작 확인

1. 브랜치에 키 포함 여부 확인:
   ```bash
   git branch --show-current
   ```
   예: `feature/SCRUM-123-test` → OK

2. 파일 스테이징 후 `git commit` (메시지 없이) 실행
3. 열린 커밋 메시지에 `SCRUM-123 ...` 이 맨 앞에 있는지 확인

---

## 5. 정리

| 항목 | 내용 |
|------|------|
| **Jira 브랜치** | 이름에 `XXX-NNN` 형식 이슈 키 포함 (예: `feature/SCRUM-123-add-x`) |
| **커밋 (자동)** | 해당 브랜치에서 `git commit` 만 하면 훅이 `SCRUM-123 feat(...): ...` 형태로 채움 |
| **커밋 (직접)** | `git commit -m "SCRUM-123 ..."` 처럼 맨 앞에 키 넣기 |
| **훅 재설치** | `python automation/jira/install_git_hook.py --repo "저장소경로"` |

이렇게 설정하면 Jira 쪽에서 브랜치/커밋 기준으로 이슈와 커밋이 연결됩니다.
