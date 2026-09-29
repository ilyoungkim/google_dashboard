# Google Search Console Dashboard

> **풀스택(Full-stack) Google Search Console 연동 대시보드**
>
> Google OAuth 2.0 인증을 통해 사용자의 Search Console 데이터를 **읽기 전용(read-only)** 으로 조회하고, 검색 트래픽·사이트·사이트맵·KPI를 시각화하는 웹 애플리케이션입니다.

---

## 아키텍처

```
┌──────────────────┐       ┌──────────────────────────────┐       ┌─────────────────────┐
│  Frontend (SPA)  │       │  Backend (FastAPI, Python)   │       │   Google APIs       │
│  React + Vite    │◀─────▶│  /auth/*  +  /api/*          │◀─────▶│  OAuth 2.0          │
│  TailwindCSS     │ cookie │  MariaDB (Fernet 암호화)     │ token │  Search Console API │
└──────────────────┘       └──────────────────────────────┘       └─────────────────────┘
```

- **백엔드**: FastAPI + Python 3.13, OAuth 2.0 Authorization Code Flow, Fernet 토큰 암호화
- **프론트엔드**: React 18 + Vite + TypeScript + TailwindCSS + Recharts + TanStack Query
- **저장소**: MariaDB(`<DB_HOST>:3306/google`) 운영 + SQLite 로컬 개발/테스트 폴백
- **DB 설정**: `config.toml`로 연결 정보 관리, `Database` 래퍼가 SQLite ↔ MySQL 방언 자동 변환
- **Dry-run 모드**: Google API 호출 없이 가상 데이터로 전체 기능 테스트 가능

---

## 빠른 시작 (Dry-run 모드)

> **Dry-run 모드**에서는 Google Cloud 프로젝트 설정 없이도 가상 데이터로 전체 기능을 테스트할 수 있습니다.

### 1. 저장소 클론 및 의존성 설치

```bash
cd google_dashboard

# Python 백엔드 의존성 설치
uv sync

# 보안 키 생성
uv run python scripts/gen_key.py
# → 출력된 TOKEN_ENCRYPTION_KEY 와 SESSION_SECRET_KEY 를 .env 에 복사
```

### 2. 환경 변수 설정

`.env` 파일이 이미 dry-run 용으로 설정되어 있습니다. 필요 시 수정:

```dotenv
# Dry-run 모드 (Google API 호출 없이 가상 데이터 사용)
DRY_RUN=true

# 보안 키 (scripts/gen_key.py 로 생성한 값)
TOKEN_ENCRYPTION_KEY=...
SESSION_SECRET_KEY=...

# Google OAuth (dry-run 에서는 더미 값도 무방)
GOOGLE_CLIENT_ID=369325489644-b7td2crdilui72qnt09j19j7rh6vvl7p.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8100/auth/callback
```

### 3. DB 설정 (config.toml)

```toml
[database]
host = "<DB_HOST>"
port = 3306
user = "<DB_USER>"
password = "<DB_PASSWORD>"
database = "google"

# true → SQLite (로컬 개발/테스트), false → MariaDB (운영)
use_sqlite = false
```

- 실제 접속 정보는 저장소에 커밋하지 말고 로컬 `config.toml`에서 관리하세요.
- `use_sqlite = true` → 로컬 SQLite 파일(`.tokens/gsc_cache.db`) 사용
- `use_sqlite = false` → MariaDB 서버 연결
- pytest 실행 시 자동으로 `use_sqlite = true` 강제

### 4. 백엔드 실행

```bash
uv run uvicorn app.main:app --reload --port 8100
```

- API 문서: http://localhost:8100/docs (Swagger UI)
- Health check: http://localhost:8100/healthz

### 5. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

- 프론트엔드: http://localhost:5173
- Vite dev server가 `/auth`, `/api` 요청을 백엔드(`:8100`)로 프록시합니다.

### 6. Dry-run 테스트

```bash
# 백엔드 단위/통합 테스트 (20개)
uv run pytest tests/ -v
```

---

## Google OAuth 연동 (실제 API 사용)

실제 Google Search Console 데이터를 조회하려면:

### 1. Google Cloud Console 설정

| 단계 | 작업 |
|------|------|
| 1 | [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 생성 |
| 2 | **API 및 서비스 → 라이브러리** → "Google Search Console API" 사용 설정 |
| 3 | **OAuth 동의 화면** 구성 (External, 앱 이름/이메일/범위) |
| 4 | **사용자 인증 정보 → OAuth 클라이언트 ID** (웹 애플리케이션) |
| 5 | **승인된 리다이렉트 URI** 에 `http://localhost:8100/auth/callback` 등록 |
| 6 | 발급된 `Client ID` 와 `Client Secret` 을 `.env` 에 기입 |

### 테스트 사용자 등록 (`403 access_denied` 해결)

OAuth 동의 화면의 사용자 유형이 **External**이고 게시 상태가 **Testing**이면, Google Cloud 프로젝트에 등록한 테스트 사용자만 로그인할 수 있습니다. 이 제한은 애플리케이션의 `/auth/callback` 이전에 Google에서 적용됩니다.

1. Google Cloud Console에서 OAuth 클라이언트가 있는 프로젝트를 엽니다.
2. **Google Auth Platform → Audience(대상)** 로 이동합니다. 기존 Console UI에서는 **API 및 서비스 → OAuth 동의 화면**에 있습니다.
3. **Test users(테스트 사용자)**에서 **Add users(사용자 추가)**를 선택합니다.
4. 로그인할 Google 계정 이메일(예: `luvdoffice@gmail.com`)을 추가하고 저장합니다.
5. 브라우저의 Google 계정을 전환하거나 시크릿 창에서 다시 로그인합니다.

Google은 테스트 OAuth 앱의 테스트 사용자 목록을 등록하는 공식 `gcloud` CLI 또는 공개 API를 제공하지 않습니다. 따라서 위 Console 화면에서 수동으로 등록해야 합니다. 앱 내부에 이메일 화이트리스트를 구현해도 Google 인증 단계 이전에 발생하는 `403 access_denied`는 해결되지 않습니다.

모든 Google 계정에 서비스를 공개하려면 게시 상태를 **In production(프로덕션)** 으로 전환하고, 요청 범위에 따라 Google OAuth 앱 검증을 진행해야 합니다. Google Workspace 조직 계정만 지원하는 앱은 Workspace 조직에 속한 프로젝트에서 사용자 유형을 **Internal**로 구성할 수 있으며, 개인 Gmail 계정은 Internal 앱에 로그인할 수 없습니다.

### 사용자별 Search Console 권한

OAuth 테스트 사용자 등록과 Search Console 데이터 권한은 별개입니다. 사용자가 로그인한 뒤 특정 사이트 데이터를 보려면 해당 Google 계정이 Search Console 속성의 사용자로 추가되어 있어야 합니다.

1. [Google Search Console](https://search.google.com/search-console/)에서 속성을 선택합니다.
2. **설정 → 사용자 및 권한**에서 사용자를 추가합니다.
3. 필요한 수준의 권한을 부여합니다. 이 대시보드는 읽기 전용 권한으로 동작합니다.
4. 사용자가 대시보드에서 다시 로그인하면 접근 가능한 속성이 사이트 선택기에 표시됩니다.

### 2. `.env` 수정

```dotenv
DRY_RUN=false
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8100/auth/callback

# 선택: 등록된 로컬 IP의 robots.txt 진단을 허용할 때만 설정
# ROBOTS_ALLOWED_LOCAL_HOSTS=127.0.0.1,192.168.0.10
```

### 3. 실행

```bash
uv run uvicorn app.main:app --reload --port 8100
```

브라우저에서 `http://localhost:5173/login` → "Google 계정으로 로그인" → OAuth 인증 → 대시보드 진입.

---

## 대시보드 사용법

1. `http://localhost:5173/login`에서 Google 계정으로 로그인합니다.
2. 상단 사이트 선택기에서 조회할 Search Console 속성을 선택합니다.
3. 기간 버튼에서 `1일`, `7일`, `28일`, `90일`, `6개월` 중 분석 기간을 고릅니다.
4. 트렌드 그래프에서 `7일 평균`, `28일 평균`, `3개월 평균`을 선택해 클릭·노출의 기준선과 비교합니다. 평균은 선택한 종료일을 기준으로 계산됩니다.
5. 필요하면 **리포트 다운로드**로 선택한 기간별 KPI, 상위 검색어·페이지, 트렌드, 진단 결과를 Markdown 파일로 내려받습니다.

### 표시되는 Search Console 데이터

| 화면 | 데이터 | 설명 |
|------|--------|------|
| KPI | 클릭, 노출, CTR, 평균 순위 | 선택한 기간의 검색 성과 요약 |
| 일별 트렌드 | 일자별 클릭·노출 | 선택한 평균 기간의 기준선과 비교 |
| 상위 검색어 / 페이지 | 검색어·페이지별 성과 | 클릭, 노출, CTR, 평균 순위 |
| 국가 / 기기 | 국가·기기별 성과 | 국가 코드와 데스크톱·모바일·태블릿별 검색 성과 |
| 검색 표시 유형 | Search Appearance | Google이 제공하는 리치 결과·표시 유형별 성과. 데이터가 없는 속성에서는 비어 있을 수 있음 |
| 사이트맵 | 제출일, 경고, 오류, 색인 수 | Search Console 사이트맵 API가 제공하는 정보 |
| 이슈 | 사이트맵, robots.txt, 성과 기반 진단 | 사이트맵 오류·경고, robots.txt, 낮은 CTR·순위 후보를 조합한 진단 |

Google Search Console API는 웹 UI의 페이지 색인 생성·Core Web Vitals·HTTPS·개선사항 문제 목록 전체를 제공하지 않습니다. 따라서 대시보드의 이슈는 API에서 확인 가능한 정보와 성과 데이터를 바탕으로 표시됩니다.

### URL 색인 검사

대시보드 하단의 **URL 색인 검사**에 전체 URL을 입력하면 Google URL Inspection API 결과를 표시합니다.

- 색인 판정과 색인 상태
- robots.txt 및 색인 허용 상태
- 페이지 가져오기 결과와 마지막 크롤링 날짜
- Google Canonical과 사용자 지정 Canonical
- 사용한 크롤러

`sc-domain:example.com` 속성도 검사할 수 있지만, 입력값은 `https://example.com/page` 형식의 전체 URL이어야 합니다. 이 API는 URL 하나씩 검사하며 Search Console 웹 UI의 전체 문제 URL 목록을 일괄 반환하지 않습니다.

### AI 유입 및 인용 데이터

현재 연동된 Search Console API는 ChatGPT, Perplexity, Gemini 등의 AI 답변 인용 횟수를 제공하지 않습니다. AI 추천 유입 그래프가 필요하면 GA4 Data API를 별도 연동해 AI 도메인 추천 트래픽을 수집해야 합니다. 이는 인용 횟수가 아니라 AI 서비스에서 실제로 유입된 방문 수입니다.

---

## 디렉토리 구조

```
google_dashboard/
├── app/                          # 백엔드 (FastAPI)
│   ├── main.py                   # FastAPI 엔트리포인트
│   ├── config.py                 # pydantic-settings 설정
│   ├── deps.py                   # 의존성 주입 (세션, GSC 클라이언트)
│   ├── auth/
│   │   ├── oauth.py              # Google OAuth 플로우
│   │   ├── routes.py             # /auth/login, /auth/callback, /auth/status, /auth/logout
│   │   ├── state.py              # CSRF state 생성/검증
│   │   └── token_store.py        # Fernet 암호화 + DB 토큰 저장소 (MariaDB/SQLite)
│   ├── api/
│   │   ├── routes.py             # /api/sites, /api/searchanalytics/query, /api/sitemaps, /api/kpi
│   │   ├── searchconsole.py      # Search Console API 클라이언트 (dry-run 지원)
│   │   └── schemas.py            # Pydantic 요청/응답 모델
│   ├── db/
│   │   ├── database.py           # MariaDB(asyncmy) + SQLite(aiosqlite) 듀얼 백엔드
│   │   └── repository.py         # 사용자/세션/프로젝트/캐시 CRUD
│   └── core/
│       ├── security.py           # Fernet 암복호화
│       ├── session.py            # 서명 쿠키 (itsdangerous)
│       └── errors.py             # 표준 에러 응답
├── frontend/                     # 프론트엔드 (React + Vite)
│   ├── src/
│   │   ├── api/                  # 백엔드 API 클라이언트
│   │   ├── auth/                 # AuthContext, AuthGuard
│   │   ├── routes/               # LoginPage, SitesPage, DashboardPage
│   │   ├── lib/                  # 유틸 (format, queryKeys)
│   │   └── styles/               # TailwindCSS 글로벌 스타일
│   └── vite.config.ts            # dev proxy → :8100
├── tests/                        # 백엔드 테스트
│   ├── conftest.py
│   ├── test_auth_flow.py
│   ├── test_token_store.py
│   └── test_api_endpoints.py
├── scripts/
│   └── gen_key.py                # Fernet 키 + 세션 키 생성
├── config.toml                   # DB 연결 설정 (MariaDB / SQLite)
├── pyproject.toml
├── .env.example
└── README.md
```

---

## API 엔드포인트

### 인증 (Auth)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/auth/login` | Google OAuth 로그인 페이지로 리다이렉트 |
| `GET` | `/auth/callback` | Google OAuth 콜백 처리 |
| `GET` | `/auth/status` | 현재 인증 상태 반환 |
| `POST` | `/auth/logout` | 로그아웃 (세션 + 토큰 삭제) |

### Search Console API (인증 필요)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/sites` | 등록된 사이트 목록 |
| `POST` | `/api/searchanalytics/query` | 검색 트래픽 분석 |
| `GET` | `/api/sitemaps?siteUrl=...` | 사이트맵 목록 |
| `POST` | `/api/urlinspection/index` | URL 색인 상태 검사 |
| `GET` | `/api/kpi?siteUrl=...&startDate=...&endDate=...` | KPI 요약 (클릭/노출/CTR/순위) |

### 헬스 체크

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/healthz` | 서버 상태 + dry_run 여부 |

---

## 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.13 | `pyproject.toml` 명시 |
| 패키지 매니저 | uv | 빠른 의존성 관리 |
| 웹 프레임워크 | FastAPI | 비동기, OpenAPI 자동 생성 |
| OAuth | google-auth-oauthlib | Authorization Code Flow |
| 암호화 | cryptography (Fernet) | AES-128 + HMAC at-rest |
| 데이터베이스 | MariaDB (asyncmy) + SQLite (aiosqlite) | 운영/개발 듀얼 백엔드 |
| 세션 | itsdangerous | 서명 쿠키 |
| 프론트엔드 | React 18 + Vite + TypeScript | SPA |
| 스타일링 | TailwindCSS | 유틸리티 퍼스트 |
| 차트 | Recharts | 검색 트래픽 시각화 |
| 상태 관리 | TanStack Query (React Query) | 서버 상태 캐싱 |
| 테스트 | pytest + pytest-asyncio | 20개 테스트 통과 ✅ |

---

## 데이터베이스 구조

운영 DB `<DB_HOST>:3306/google` (MariaDB, InnoDB, utf8mb4)

| 테이블 | 설명 | 주요 컬럼 |
|--------|------|----------|
| `users` | Google 사용자 계정 | `user_id`(PK), `email`, `created_at` |
| `sessions` | OAuth 토큰 (Fernet 암호화) | `session_id`(PK), `user_id`(FK), `access_token_ciphertext`, `refresh_token_ciphertext`, `expires_at` |
| `projects` | Search Console 사이트 | `id`(PK), `user_id`(FK), `site_url`, `permission_level` |
| `analytics_cache` | Search Analytics 캐시 (TTL 6h) | `id`(PK), `project_id`(FK), `query_hash`, `data_json` |
| `sitemaps_cache` | Sitemaps 캐시 (TTL 24h) | `id`(PK), `project_id`(FK), `data_json` |
| `oauth_states` | OAuth CSRF state (단기 저장) | `state`(PK), `created_at` |

> FK 관계: `users` → `sessions`, `users` → `projects` → `analytics_cache` / `sitemaps_cache` (ON DELETE CASCADE)

### DDL (MariaDB)

`app/db/database.py`의 `_create_tables_mysql_inner()`가 앱 시작 시 실행하는 스키마입니다.
모든 시각 컬럼은 unix timestamp(`DOUBLE`)로 저장합니다.

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id     VARCHAR(255) PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP())
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS projects (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    user_id     VARCHAR(255) NOT NULL,
    site_url    TEXT NOT NULL,
    permission_level VARCHAR(50) NOT NULL DEFAULT 'siteOwner',
    created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
    UNIQUE KEY uq_user_site (user_id, site_url(255)),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS analytics_cache (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    project_id  INT NOT NULL,
    query_hash  VARCHAR(64) NOT NULL,
    data_json   LONGTEXT NOT NULL,
    fetched_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
    expires_at  DOUBLE NOT NULL,
    UNIQUE KEY uq_project_hash (project_id, query_hash),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sitemaps_cache (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    project_id  INT NOT NULL,
    data_json   LONGTEXT NOT NULL,
    fetched_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
    expires_at  DOUBLE NOT NULL,
    UNIQUE KEY (project_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sessions (
    session_id  VARCHAR(64) PRIMARY KEY,
    user_id     VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL DEFAULT '',
    scopes      TEXT NOT NULL DEFAULT '[]',
    access_token_ciphertext  TEXT NOT NULL DEFAULT '',
    refresh_token_ciphertext TEXT NOT NULL DEFAULT '',
    access_token_expires_at  DOUBLE NOT NULL DEFAULT 0.0,
    created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
    updated_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS oauth_states (
    state       VARCHAR(64) PRIMARY KEY,
    created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP())
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- MariaDB는 CREATE INDEX IF NOT EXISTS를 지원하지 않으므로,
-- 이미 존재하는 경우(duplicate key) 오류를 무시하고 실행한다.
CREATE INDEX idx_projects_user ON projects(user_id);
CREATE INDEX idx_analytics_cache_project ON analytics_cache(project_id);
CREATE INDEX idx_sitemaps_cache_project ON sitemaps_cache(project_id);
CREATE INDEX idx_sessions_user ON sessions(user_id);
```

### DDL (SQLite, 로컬 개발/테스트)

`use_sqlite = true`일 때 `_create_tables_sqlite()`가 실행하는 스키마입니다.
MariaDB와 논리적으로 동일하며, 타입과 자동 증가 문법만 다릅니다.

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id     TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    created_at  REAL NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    site_url    TEXT NOT NULL,
    permission_level TEXT NOT NULL DEFAULT 'siteOwner',
    created_at  REAL NOT NULL DEFAULT (unixepoch()),
    UNIQUE(user_id, site_url)
);

CREATE TABLE IF NOT EXISTS analytics_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    query_hash  TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    fetched_at  REAL NOT NULL DEFAULT (unixepoch()),
    expires_at  REAL NOT NULL,
    UNIQUE(project_id, query_hash)
);

CREATE TABLE IF NOT EXISTS sitemaps_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    data_json   TEXT NOT NULL,
    fetched_at  REAL NOT NULL DEFAULT (unixepoch()),
    expires_at  REAL NOT NULL,
    UNIQUE(project_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    email       TEXT NOT NULL DEFAULT '',
    scopes      TEXT NOT NULL DEFAULT '[]',
    access_token_ciphertext  TEXT NOT NULL DEFAULT '',
    refresh_token_ciphertext TEXT NOT NULL DEFAULT '',
    access_token_expires_at  REAL NOT NULL DEFAULT 0.0,
    created_at  REAL NOT NULL DEFAULT (unixepoch()),
    updated_at  REAL NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state       TEXT PRIMARY KEY,
    created_at  REAL NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_cache_project ON analytics_cache(project_id);
CREATE INDEX IF NOT EXISTS idx_sitemaps_cache_project ON sitemaps_cache(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
```

---

## 보안

- **OAuth Scope**: `webmasters.readonly` — 읽기 전용
- **CSRF 방어**: `state` 파라미터 + 서명 쿠키
- **토큰 저장**: Fernet(AES-128-CBC + HMAC-SHA256) 으로 at-rest 암호화
- **세션 쿠키**: `HttpOnly`, `SameSite=Lax`, 서명 + 만료 시간
- **자동 Refresh**: Access Token 만료 시 refresh_token 으로 자동 갱신
- **CORS**: 프론트엔드 origin 화이트리스트

---

## 라이선스

MIT
