# 🚂 중앙아시아 철도 운임 주간 리포트

중국~중앙아시아 노선의 철도 운임 및 물류 동향을 자동 수집해 Notion DB에 저장하는 자동화 도구입니다.

## 수집 노선
- 중국 → 카자흐스탄
- 중국 → 우즈베키스탄
- 중국 → 키르기스스탄
- 중국 → 투르크메니스탄
- 중국 → 러시아 (TSR)
- 한국/일본 → 중앙아시아 (중국 경유)

## 실행 주기
매주 월요일 오전 10시 (KST) 자동 실행

---

## 세팅 방법

### 1. 이 저장소를 GitHub에 업로드
GitHub에서 새 저장소(repository) 생성 후 파일 전체 업로드

### 2. Notion 연동 정보 입력
GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret

| Secret 이름          | 값                                      |
|----------------------|-----------------------------------------|
| `NOTION_TOKEN`       | Notion 인테그레이션 토큰 (`ntn_...`)     |
| `NOTION_DATABASE_ID` | `138f2c4f-3b02-4f0a-a4e1-aa00131d4421` |

### 3. 수동 테스트 실행
GitHub 저장소 → Actions 탭 → "중앙아시아 철도 운임 주간 수집" → Run workflow

---

## 파일 구조
```
ca-rail-report/
├── src/
│   └── collector.py          # 메인 수집 스크립트
├── .github/
│   └── workflows/
│       └── weekly_collect.yml  # GitHub Actions 자동화
├── requirements.txt
└── README.md
```
