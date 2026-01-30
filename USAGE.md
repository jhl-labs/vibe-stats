# vibe-stats 사용 가이드

GitHub Organization(또는 개인 계정)의 코드 기여 통계를 수집하고 표시하는 CLI 도구입니다.

## 설치

```bash
pip install -e ".[dev]"
```

## 기본 사용법

```bash
vibe-stats <ORG> --token <GITHUB_TOKEN>
```

- `<ORG>`: GitHub Organization 또는 사용자 이름 (필수)
- `--token`: GitHub API 토큰 (환경변수 `GITHUB_TOKEN`으로 대체 가능)

### 환경변수로 토큰 설정

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
vibe-stats my-org
```

## 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--token TEXT` | `$GITHUB_TOKEN` | GitHub API 토큰 |
| `--top-n INTEGER` | `10` | 상위 기여자 표시 수 |
| `--since TEXT` | 없음 | 시작 날짜 필터 (YYYY-MM-DD) |
| `--until TEXT` | 없음 | 종료 날짜 필터 (YYYY-MM-DD) |
| `--include-forks` | 꺼짐 | 포크된 레포지토리 포함 |
| `--format [table\|json\|csv]` | `table` | 출력 포맷 |
| `--no-cache` | 꺼짐 | 캐시 비활성화 |
| `--version` | - | 버전 표시 |
| `--help` | - | 도움말 표시 |

## 사용 예시

### 기본 실행 (터미널 테이블 출력)

```bash
vibe-stats my-org --token ghp_xxxxxxxxxxxx
```

### 개인 계정 통계 조회

Organization이 아닌 개인 계정도 지원합니다. Org API가 404를 반환하면 자동으로 사용자 레포지토리를 조회합니다.

```bash
vibe-stats my-username
```

### 기간 필터링

특정 기간의 통계만 조회합니다.

```bash
# 2024년 전체
vibe-stats my-org --since 2024-01-01 --until 2024-12-31

# 2024년 하반기
vibe-stats my-org --since 2024-07-01 --until 2024-12-31

# 특정 날짜 이후
vibe-stats my-org --since 2024-06-01
```

### 출력 포맷 변경

```bash
# JSON 출력
vibe-stats my-org --format json

# JSON을 파일로 저장
vibe-stats my-org --format json > report.json

# CSV 출력 (기여자 데이터)
vibe-stats my-org --format csv

# CSV를 파일로 저장
vibe-stats my-org --format csv > contributors.csv
```

### 포크 포함

기본적으로 소스 레포지토리만 조회합니다. 포크된 레포도 포함하려면:

```bash
vibe-stats my-org --include-forks
```

### 상위 기여자 수 변경

```bash
# 상위 20명 표시
vibe-stats my-org --top-n 20
```

### 캐시 비활성화

API 응답은 `~/.cache/vibe-stats/`에 1시간 동안 캐시됩니다. 최신 데이터가 필요하면:

```bash
vibe-stats my-org --no-cache
```

### 옵션 조합

```bash
# 2024년 통계를 JSON으로, 포크 포함, 캐시 없이
vibe-stats my-org \
  --since 2024-01-01 \
  --until 2024-12-31 \
  --format json \
  --include-forks \
  --no-cache
```

## 출력 형식

### table (기본)

터미널에 Rich 테이블로 출력됩니다:
- 요약 (레포 수, 커밋 수, additions/deletions)
- 언어 분포 (바 차트, 상위 15개)
- 상위 기여자 랭킹

수집에 실패한 레포가 있으면 경고 메시지가 표시됩니다.

### json

전체 리포트를 JSON으로 출력합니다. 프로그래밍적 처리에 적합합니다.

```bash
vibe-stats my-org --format json | jq '.contributors[:5]'
```

### csv

기여자 데이터를 CSV로 출력합니다. 스프레드시트 분석에 적합합니다.

```
username,commits,additions,deletions
alice,150,12000,3000
bob,120,8000,2500
```

## 에러 처리

- **빈 레포지토리**: 자동으로 건너뛰고 나머지 레포를 처리합니다.
- **접근 불가 레포**: 실패한 레포는 기록되고, 리포트에 경고로 표시됩니다.
- **Rate Limit**: 잔여 요청이 부족하면 자동으로 리셋 시각까지 대기합니다.
- **통계 생성 지연**: GitHub의 202 응답에 대해 자동으로 재시도합니다.

## 테스트 실행

```bash
pytest tests/ -v
```
