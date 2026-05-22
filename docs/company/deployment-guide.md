# 배포 가이드

## 배포 환경
- dev: feature 브랜치 자동 배포 (PR 열릴 때)
- staging: main 브랜치 머지 시 자동 배포
- production: 수동 트리거 (GitHub Actions)

## 배포 프로세스
1. PR 머지 → staging 자동 배포 (약 5분 소요)
2. staging QA 확인 (담당 QA 엔지니어)
3. 팀장 배포 승인
4. GitHub Actions에서 production 배포 트리거
5. 배포 완료 후 Slack #deploy 채널 공지

## 배포 금지 시간
- 금요일 17:00 이후 ~ 월요일 10:00
- 공휴일 전날 14:00 이후
- 월말 마감일 (매월 마지막 영업일 15:00 이후)

## 롤백 절차
문제 발생 시 GitHub Actions에서 이전 성공 배포를 선택하여 재배포.
즉각 롤백이 필요한 경우: 인프라팀 슬랙(@oncall) 태그.

## 모니터링
- Grafana 대시보드: grafana.acmecorp.com
- 에러 알림: Sentry → Slack #alerts
- 응답시간 임계값: p99 500ms 초과 시 알림
