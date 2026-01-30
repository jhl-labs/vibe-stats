# vibe-stats

GitHub Organization의 코드 기여 통계를 수집·분석하는 CLI 도구입니다.

Git clone 없이 GitHub REST API만으로 커밋 수, 코드 변경량(additions/deletions), 언어 비율, 기여자별 통계를 산출합니다.

## 주요 기능

- **레포지토리 통계 수집** — Org 전체 레포의 커밋 수, CLOC, 언어 분포를 집계
- **기여자 랭킹** — 커밋 수·additions·deletions 기준 기여자 순위
- **기간 필터링** — `--since` / `--until`로 특정 기간만 조회
- **다양한 출력 포맷** — 터미널 테이블, JSON, CSV 지원
- **비동기 병렬 처리** — asyncio + httpx로 대규모 Org도 처리
- **파일 캐싱** — API 응답을 디스크에 캐시하여 반복 조회 최적화
- **에러 복구** — 개별 레포 실패 시 graceful degradation

## 설치

```bash
pip install -e .
```

개발 환경:

```bash
pip install -e ".[dev]"
```

### 요구사항

- Python 3.10+
- GitHub Personal Access Token

## 빠른 시작

```bash
# 환경변수로 토큰 설정
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Organization 통계 조회
vibe-stats my-org

# 개인 계정도 지원
vibe-stats my-username

# 기간 지정
vibe-stats my-org --since 2024-01-01 --until 2024-12-31

# JSON 출력
vibe-stats my-org --format json > report.json
```

## 사용법

```
vibe-stats <org> [OPTIONS]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--token TEXT` | `$GITHUB_TOKEN` | GitHub API 토큰 |
| `--top-n INTEGER` | `10` | 상위 기여자 표시 수 |
| `--since TEXT` | - | 시작 날짜 (YYYY-MM-DD) |
| `--until TEXT` | - | 종료 날짜 (YYYY-MM-DD) |
| `--include-forks` | 꺼짐 | 포크된 레포 포함 |
| `--format [table\|json\|csv]` | `table` | 출력 포맷 |
| `--no-cache` | 꺼짐 | 캐시 비활성화 |

자세한 사용법은 [USAGE.md](USAGE.md)를 참고하세요.

## 출력 예시

```
╭──────────────────────────────────────────╮
│         vibe-stats: my-org               │
│         Period: 2024-01-01 ~ 2024-12-31  │
╰──────────────────────────────────────────╯

📊 Summary
  Repositories : 42
  Total Commits: 12,345
  Additions    : 1,234,567
  Deletions    :   456,789

📝 Language Distribution
  Python     ████████████████████  62.3%
  TypeScript ████████░░░░░░░░░░░░  25.1%
  Go         ███░░░░░░░░░░░░░░░░░   8.4%
  Other      █░░░░░░░░░░░░░░░░░░░   4.2%

👥 Top Contributors
  ┌────┬──────────────┬─────────┬───────────┬──────────┐
  │ #  │ Username     │ Commits │ Additions │ Deletions│
  ├────┼──────────────┼─────────┼───────────┼──────────┤
  │  1 │ alice        │   1,234 │   123,456 │   45,678 │
  │  2 │ bob          │     987 │    98,765 │   34,567 │
  │  3 │ charlie      │     654 │    65,432 │   23,456 │
  └────┴──────────────┴─────────┴───────────┴──────────┘
```

## 아키텍처

```
CLI (click) → Orchestrator → Aggregator → GitHub API Client → GitHub REST API
                                  ↓
                            Report Renderer (rich)
```

자세한 아키텍처는 [ARCHITECTURE.md](ARCHITECTURE.md)를 참고하세요.

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10+ |
| HTTP | httpx (async) |
| CLI | click |
| 터미널 UI | rich |
| 비동기 | asyncio |
| 테스트 | pytest, pytest-asyncio |

## 테스트

```bash
pytest tests/ -v
```

## 라이선스

이 프로젝트는 [GNU General Public License v3.0](LICENSE) 라이선스를 따릅니다.
