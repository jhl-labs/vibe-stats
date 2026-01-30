# vibe-stats Architecture

## 1. 프로젝트 개요

**vibe-stats**는 GitHub Organization의 코드 기여 통계를 수집·분석하여 터미널에 리포트를 출력하는 CLI 도구이다. Git clone 없이 GitHub API만으로 커밋 수, CLOC(additions/deletions), 언어 비율 등을 산출한다.

---

## 2. Functional Requirements (FR)

| ID | 요구사항 | 설명 |
|----|----------|------|
| FR-1 | 레포지토리 목록 조회 | 지정된 Org의 전체 레포지토리 목록을 가져온다 |
| FR-2 | 커밋 수 집계 | 레포지토리별·기여자별 커밋 수를 집계한다 |
| FR-3 | CLOC 산출 | additions, deletions 등 코드 변경량을 계산한다 |
| FR-4 | 언어 비율 계산 | 레포지토리별·Org 전체의 언어 사용 비율을 산출한다 |
| FR-5 | 리포트 출력 | 종합 통계를 터미널에 보기 좋게 출력한다 |
| FR-6 | 기간 필터링 | 특정 기간(since/until)에 해당하는 통계만 조회한다 |
| FR-7 | 기여자별 통계 | 기여자(author)별로 커밋 수·CLOC를 분류하여 보여준다 |

---

## 3. Non-Functional Requirements (NFR)

| ID | 요구사항 | 설명 |
|----|----------|------|
| NFR-1 | Rate Limit 준수 | GitHub API rate limit을 초과하지 않도록 요청을 제어한다 |
| NFR-2 | Clone 불필요 | git clone 없이 API만으로 모든 통계를 수집한다 |
| NFR-3 | 응답 시간 | 비동기 처리로 대규모 Org에서도 합리적인 시간 내에 결과를 반환한다 |
| NFR-4 | 캐싱 | 반복 조회 시 API 호출을 줄이기 위해 응답을 캐싱한다 |
| NFR-5 | 에러 복구 | API 오류·네트워크 장애 시 재시도 및 graceful degradation을 지원한다 |
| NFR-6 | 보안 | GitHub 토큰 등 민감 정보가 로그나 출력에 노출되지 않는다 |

---

## 4. 시스템 아키텍처

```
┌─────────────┐
│  CLI Layer  │  click 기반 인터페이스
└──────┬──────┘
       │
┌──────▼──────┐
│ Orchestrator│  워크플로우 조율, 비동기 실행
└──────┬──────┘
       │
  ┌────┴────┐
  │         │
┌─▼───┐ ┌──▼──────────┐
│ API │ │    Data      │
│Client│ │ Aggregator  │
└─┬───┘ └──┬──────────┘
  │         │
  │    ┌────▼─────────┐
  │    │   Report     │
  │    │  Renderer    │
  │    └──────────────┘
  │
┌─▼────────────┐
│  GitHub API  │
│ (REST+GraphQL)│
└──────────────┘
```

### 컴포넌트 설명

| 컴포넌트 | 역할 |
|----------|------|
| **CLI Layer** | 사용자 입력 파싱, 인자 검증, 진행 상황 표시 |
| **Orchestrator** | 전체 수집 흐름 조율, 비동기 태스크 관리 |
| **GitHub API Client** | REST/GraphQL API 호출, rate limit 관리, 재시도 처리 |
| **Data Aggregator** | 수집된 원시 데이터를 집계·변환하여 통계 모델 생성 |
| **Report Renderer** | 집계된 데이터를 터미널 테이블·차트로 렌더링 |

---

## 5. GitHub API 사용 전략

### Clone 없이 통계 수집

Git clone을 수행하지 않고 GitHub API만으로 통계를 산출한다.

| 데이터 | API | 비고 |
|--------|-----|------|
| 레포 목록 | REST `GET /orgs/{org}/repos` | pagination 처리 필요 |
| 커밋 목록 | REST `GET /repos/{owner}/{repo}/commits` | since/until 파라미터 활용 |
| 커밋 상세 (CLOC) | REST `GET /repos/{owner}/{repo}/commits/{sha}` | additions/deletions 포함 |
| 언어 비율 | REST `GET /repos/{owner}/{repo}/languages` | 바이트 단위 반환 |
| 기여자 통계 | REST `GET /repos/{owner}/{repo}/stats/contributors` | 주간 단위 집계, 비동기 생성 |

### REST + GraphQL 하이브리드 전략

- **REST API**: 커밋 상세, 언어 비율, 기여자 통계 등 전용 엔드포인트가 있는 경우
- **GraphQL API**: 여러 레포의 데이터를 한 번에 조회하여 API 호출 수를 절감할 때 활용

### Rate Limit 관리

- `X-RateLimit-Remaining` 헤더를 모니터링하여 잔여 횟수가 임계값 이하일 때 대기
- 429 응답 시 `Retry-After` 헤더에 따라 자동 재시도
- 동시 요청 수를 `asyncio.Semaphore`로 제한

---

## 6. 데이터 모델

`dataclass` 기반으로 통계 데이터를 구조화한다.

```python
@dataclass
class LanguageStats:
    language: str
    bytes: int
    percentage: float

@dataclass
class ContributorStats:
    username: str
    commits: int
    additions: int
    deletions: int

@dataclass
class RepoStats:
    name: str
    full_name: str
    total_commits: int
    total_additions: int
    total_deletions: int
    languages: list[LanguageStats]
    contributors: list[ContributorStats]

@dataclass
class OrgReport:
    org: str
    period_start: str | None
    period_end: str | None
    total_repos: int
    total_commits: int
    total_additions: int
    total_deletions: int
    languages: list[LanguageStats]
    contributors: list[ContributorStats]
    repos: list[RepoStats]
```

---

## 7. CLI 인터페이스 설계

`click` 라이브러리 기반으로 구현한다.

### 명령어

```
vibe-stats <org> [OPTIONS]
```

### 인자 및 옵션

| 인자/옵션 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `org` | string | Y | GitHub Organization 이름 |
| `--token` | string | N | GitHub API 토큰 (미지정 시 `GITHUB_TOKEN` 환경변수 사용) |
| `--since` | date | N | 집계 시작 날짜 (YYYY-MM-DD) |
| `--until` | date | N | 집계 종료 날짜 (YYYY-MM-DD) |
| `--format` | choice | N | 출력 형식: `table` (기본), `json`, `csv` |
| `--top-n` | int | N | 상위 N명 기여자만 표시 |

### 출력 예시

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

---

## 8. 기술 스택

| 구분 | 기술 | 용도 |
|------|------|------|
| 언어 | Python 3.10+ | 타입 힌트, match 문 등 최신 문법 활용 |
| HTTP 클라이언트 | httpx | async 지원, HTTP/2 지원 |
| CLI 프레임워크 | click | 인자 파싱, 서브커맨드 지원 |
| 터미널 UI | rich | 테이블, 프로그레스 바, 컬러 출력 |
| 비동기 | asyncio | 동시 API 호출로 성능 최적화 |
| 테스트 | pytest + pytest-asyncio | 비동기 테스트 지원 |
| 패키지 관리 | pyproject.toml | PEP 621 표준 |

---

## 9. 프로젝트 디렉토리 구조

```
vibe-stats/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── src/
│   └── vibe_stats/
│       ├── __init__.py
│       ├── cli.py              # CLI 엔트리포인트 (click)
│       ├── orchestrator.py     # 워크플로우 조율
│       ├── github/
│       │   ├── __init__.py
│       │   ├── client.py       # GitHub API 클라이언트
│       │   ├── graphql.py      # GraphQL 쿼리 헬퍼
│       │   └── rate_limit.py   # Rate Limit 관리
│       ├── models.py           # 데이터 모델 (dataclass)
│       ├── aggregator.py       # 데이터 집계·변환
│       └── renderer.py         # 리포트 렌더링 (rich)
└── tests/
    ├── __init__.py
    ├── test_client.py
    ├── test_aggregator.py
    └── test_renderer.py
```

---

## 10. 제약사항 및 리스크

| # | 항목 | 설명 | 대응 방안 |
|---|------|------|-----------|
| 1 | 10K+ 커밋 제한 | REST API pagination 상한으로 10,000건 이상 조회 불가 | GraphQL로 보완, 기간 분할 조회 |
| 2 | Rate Limit | 인증 토큰 기준 시간당 5,000회 제한 | 요청 최적화, 캐싱, 조건부 요청(ETag) |
| 3 | Stats API 지연 | `/stats/contributors`는 비동기 생성으로 202 응답 가능 | 재시도 로직 (backoff) 구현 |
| 4 | Private 레포 | 토큰 권한에 따라 접근 불가한 레포 존재 | 에러 무시 후 접근 가능한 레포만 집계 |
| 5 | Fork 레포 | Fork된 레포 포함 시 통계 왜곡 가능 | `--include-forks` 옵션으로 제어 |
| 6 | 대규모 Org | 수백 개 레포 보유 Org의 경우 처리 시간 증가 | 비동기 병렬 처리, 프로그레스 바 표시 |
| 7 | API 변경 | GitHub API 스펙 변경 시 호환성 문제 | API 버전 헤더 명시, 응답 스키마 검증 |

---

## 11. 구현 우선순위

### Phase 1 — MVP

- GitHub API 클라이언트 (REST) 구현
- Org 레포 목록 조회
- 레포별 커밋 수 집계
- 언어 비율 조회
- 기본 터미널 테이블 출력
- CLI 인터페이스 (`org`, `--token`)

### Phase 2 — 최적화

- 비동기 병렬 처리 (asyncio + httpx)
- Rate Limit 관리 및 자동 재시도
- CLOC (additions/deletions) 집계
- 기여자별 통계
- 기간 필터링 (`--since`, `--until`)
- 캐싱 레이어

### Phase 3 — 고도화

- GraphQL API 통합 (호출 수 절감)
- JSON/CSV 출력 포맷
- 프로그레스 바 및 상세 진행 표시
- 에러 복구 및 부분 결과 출력
- 설정 파일 지원 (`.vibe-stats.toml`)
