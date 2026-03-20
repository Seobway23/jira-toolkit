# -*- coding: utf-8 -*-
"""결재 시스템 Jira 이슈 자동 생성 스크립트"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dev_workflow import create_jira_issue, slugify, JIRA_BASE

summary = "Add approval workflow sub-pages and nested layout"
description = (
    "결재 시스템 서브페이지 전체 구축\n"
    "- 기안함 (초안/작성 페이지)\n"
    "- 수신함 (결재 대기/예정)\n"
    "- 발신함\n"
    "- 완료/반려/참조 함\n"
    "- 보관함\n"
    "- 전체 문서 (관리자)\n"
    "- 문서 상세 페이지\n"
    "- 결재선 설정\n"
    "- ApprovalLayout 중첩 라우터 레이아웃\n"
    "- ApprovalListTable 공통 컴포넌트\n"
    "- 라우터 구조 결재 전용 레이아웃으로 재편"
)

issue = create_jira_issue(
    summary=summary,
    description=description,
    issue_type="Story",
    story_points=5,
)
print(f"ISSUE_KEY={issue['key']}")
print(f"ISSUE_URL={issue['url']}")
