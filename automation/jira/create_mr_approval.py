# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dev_workflow import create_pr, transition_jira_to_review

source_branch = "feature/SCRUM-47-approval-workflow-sub-pages"
target_branch = "dev"
title = "SCRUM-47: Add approval workflow sub-pages and nested layout"
body = """## Related Issues
- SCRUM-47

## Summary
- ApprovalLayout 중첩 라우터 레이아웃 추가 (사이드바 네비게이션 포함)
- 결재 서브페이지 전체 구축: 수신함(대기/예정), 발신함, 완료, 반려, 참조, 보관함
- 기안 페이지 및 다양한 결재 양식 (일반기안, 경비보고, 회의록, 법인카드 등)
- 문서 상세, 전체 문서(관리자), 결재선 설정 페이지
- ApprovalListTable 공통 컴포넌트
- 라우터를 ApprovalLayout 중첩 구조로 재편

## Test plan
- [ ] 결재 → 수신함/발신함/완료/반려/참조 페이지 네비게이션 확인
- [ ] 기안함 및 기안 작성 페이지 동작 확인
- [ ] ApprovalLayout 사이드바 활성 상태 확인
- [ ] 모바일/태블릿 반응형 확인

🤖 Generated with Claude Code"""

url = create_pr(source_branch, target_branch, title, body)
print(f"MR_URL={url}")
transition_jira_to_review("SCRUM-47")
