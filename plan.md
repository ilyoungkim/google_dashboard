# Google Search Console 연동 아키텍처 계획 (plan.md)

> **목적**: Google OAuth 2.0 인증을 통해 사용자의 Google 계정을 안전하게 인증하고, Search Console API를 **읽기 전용(read-only)** 으로 호출하여 검색 트래픽·사이트·사이트맵 등 데이터를 조회하는 **풀스택(백엔드 + 프론트엔드) 아키텍처**를 설계한다.
>
> **현재 워크스페이스 상태**: `pyproject.toml`(Python ≥ 3.13), `main.py`(기본 템플릿), 빈 `README.md`만 존재하는 초기 프로젝트. 본 plan을 기준으로 백엔드(FastAPI) + 프론트엔드(React/Vite)를 0부터 구축한다.

---

## 1. 아키텍처 개요 (High-Level)

### 1.1 핵심 요구사항

| # | 요구사항 | 비고 |
|---|----------|------|
| R1 | Google OAuth 2.0 로그인 플로우 지원 | Authorization Code Flow (웹 서버 앱) |
| R2 | **Read-only** Scope 만 사용 | `https://www.googleapis.com/auth/webmasters.readonly` |
| R3 | Access Token 만료 시 자동 Refresh | `refresh_token` 장기 보관 |
| R4 | 토큰 안전 저장 | AES(Fernet) 기반 at-rest 암호화 |
| R5 | CSRF 방어 | `state` 파라미터 + 세션 쿠키 |
| R6 | 향후 확장성 | 멀티 유저, 캐싱, 대시보드 UI 추가 용이 |

### 1.2 시스템 컴포넌트 다이어그램

```
┌──────────────────┐                              ┌──────────────────────────────┐                  ┌─────────────────────┐
│  Frontend SPA    │                              │  Backend (FastAPI, Python)   │                  │   Google APIs       │
│  (React + Vite)  │                              │                              │                  │                     │
│                  │   ① /auth/login (브라우저)    │  ┌────────────────────────┐  │  ②              │ ┌─────────────────┐ │
│  ┌────────────┐  │ ───────────────────────────▶ │  │  /auth/*  (OAuth)      │  │ ──────────────▶ │ │ OAuth 2.0       │ │
│  │ /login     │  │                              │  │   - login              │  │                  │ │   accounts.     │ │
│  │ /sites     │  │   ② Google OAuth 동의         │  │   - callback           │  │ ◀────────────── │ │   google.com     │ │
│  │ /dashboard │  │ ◀─────────────────────────── │  │   - status, logout     │  │  ③ code → token  │ └─────────────────┘ │
│  └────────────┘  │                              │  └────────┬───────────────┘  │                  │ ┌─────────────────┐ │
│        ▲         │   ⑤ JSON API (with cookie)    │           │ ④ 토큰 암호화 저장   │                  │ │ Search Console  │ │
│        │         │ ◀──────────────────────────▶ │  ┌────────▼───────────────┐  │  ⑥ (서버→서버)    │ │   googleapis.   │ │
│        │         │                              │  │  Token Store (Fernet)  │  │ ──────────────▶ │ │   com/          │ │
│        │         │                              │  └────────┬───────────────┘  │                  │ │   webmasters/v3 │ │
│        │         │                              │  ┌────────▼───────────────┐  │ ◀────────────── │ └─────────────────┘ │
│        │         │                              │  │  /api/*  (Read-only)   │  │  ⑦ 결과 반환      │                     │
│        │         │                              │  │   - sites              │  │                  │                     │
│        └─────────┼──────────────────────────────│  │   - searchAnalytics    │  │                  │                     │
│                  │                              │  │   - sitemaps           │  │                  │                     │
└──────────────────┘                              │  └────────────────────────┘  │                  └─────────────────────┘
                                                  └──────────────────────────────┘
```

### 1.3 데이터 흐름 (요약)

1. 사용자가 `GET /auth/login` 호출 → 백엔드가 state 생성 후 Google OAuth URL로 **302 리다이렉트**.
2. Google 로그인/동의 완료 → `GET /auth/callback?code=...&state=...` 로 콜백.
3. 백엔드가 `code` → `access_token` + `refresh_token` 교환 → **암호화**하여 Token Store에 저장.
4. 세션 쿠키(예: `session_id`) 발급 → 사용자에게 반환.
5. 사용자가 `GET /api/sites` 등 호출 → 세션으로 토큰 로드 → 만료 시 refresh → Search Console API 호출 → JSON 응답.

---

## 2. Google Cloud Console 사전 설정 (1회)

> 백엔드 코드 작성 전, Google Cloud Console에서 다음을 수행한다.

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 1 | 프로젝트 생성 | `GCP_PROJECT_ID` |
| 2 | **API 및 서비스 → 라이브러리** → "Google Search Console API" 사용 설정 | API 활성화 |
| 3 | **API 및 서비스 → OAuth 동의 화면** 구성 (External, 앱 이름/이메일/범위) | 동의 화면 게시 |
| 4 | **사용자 인증 정보 → 만들기 → OAuth 클라이언트 ID** (애플리케이션 유형: **웹 애플리케이션**) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| 5 | **승인된 리다이렉트 URI** 에 콜백 URL 등록 (개발: `http://localhost:8100/auth/callback`, 운영: `https://yourdomain.com/auth/callback`) | Redirect URI |
| 6 | **API 범위** 추가: `https://www.googleapis.com/auth/webmasters.readonly` | Scope 확정 |
| 7 | (선택) **앱 검증** 준비 – 프로덕션 출시 전 Google 심사 필요 | Verification |

---

## 3. 기술 스택

| 영역 | 선택 | 근거 |
|------|------|------|
| 언어 | **Python 3.13** | `pyproject.toml`에 명시됨, 최신 기능 활용 |
| 패키지 매니저 | **uv** | 빠른 의존성 관리, `pyproject.toml` 네이티브 |
| 웹 프레임워크 | **FastAPI** | 비동기, OpenAPI 자동 생성, 타입 기반 검증 |
| OAuth 라이브러리 | `google-auth-oauthlib`, `google-auth`, `google-api-python-client` | Google 공식, PKCE/state 내장 |
| 설정 관리 | `pydantic-settings` | 타입 안전 env 로딩, `.env` 자동 파싱 |
| 토큰 암호화 | `cryptography` (Fernet) | 대칭키 AES-128-CBC + HMAC, at-rest 보호 |
| 데이터베이스 | **MariaDB** (asyncmy) + **SQLite** (aiosqlite) 폴백 | 운영: MariaDB, 개발/테스트: SQLite |
| DB 설정 | `config.toml` | 별도 설정 파일로 DB 연결 정보 관리 |
| 세션 저장 | `itsdangerous` (서명 쿠키) 또는 서버사이드 세션(파일/Redis) | 무상태 vs 상태 저장 중 선택 가능 |
| HTTP 클라이언트 | `httpx` (FastAPI와 비동기 통합) | Search Console REST 직접 호출 시 |
| 테스트 | `pytest`, `pytest-asyncio`, `httpx` Mock | OAuth 플로우 단위/통합 테스트 |
| 린팅/포맷 | `ruff`, `mypy` | 코드 품질 |
| **프론트엔드** | **React 18 + Vite + TypeScript** | 모던 SPA, 빠른 HMR, 타입 안전 |
| UI 라이브러리 | **TailwindCSS + shadcn/ui** | 대시보드 컴포넌트 빠른 조립 |
| 차트 | **Recharts** (또는 visx/Tremor) | 검색 트래픽 시각화 |
| 라우팅 | **React Router v6** | `/login`, `/sites`, `/dashboard/:siteUrl` |
| 상태관리 | **TanStack Query (React Query)** | 서버 상태 캐싱, 자동 재검증 |
| 폼/검증 | **react-hook-form + zod** | 입력 검증 |
| HTTP | **fetch wrapper** with `credentials: 'include'` | 쿠키 기반 세션 |
| 테스트 | **Vitest + Testing Library + Playwright** | 컴포넌트 + E2E |

> **선택지**: `google-api-python-client`는 편의성이 높지만 무겁다. 단순한 endpoints만 쓴다면 `httpx`로 직접 호출해도 좋다. 본 plan은 **두 방식 모두 지원**하도록 추상화 계층(`SearchConsoleClient`)을 둔다.
>
> **프론트엔드 ↔ 백엔드 통신**: 동일 도메인(예: `https://app.yourdomain.com`)에서 SPA와 FastAPI를 함께 서빙(권장)하거나, 별도 도메인(`https://api.yourdomain.com` + `https://app.yourdomain.com`)을 두고 CORS로 화이트리스트 한다. 본 plan은 **운영 단순화를 위해 단일 도메인**을 권장한다.

---

## 4. 디렉토리 구조

```
google_dashboard/
├── pyproject.toml
├── uv.lock                      # uv 잠금 파일
├── .env.example                 # 환경 변수 템플릿
├── .gitignore
├── README.md
├── plan.md                      # 본 문서
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 엔트리포인트
│   ├── config.py                # Settings (pydantic-settings)
│   ├── deps.py                  # 의존성 주입 (현재 유저/토큰)
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── oauth.py             # OAuth 클라이언트 팩토리 + 플로우 헬퍼
│   │   ├── routes.py            # /auth/login, /auth/callback, /auth/status, /auth/logout
│   │   ├── token_store.py       # 암호화 + SQLite DB 저장 (TokenStore)
│   │   └── state.py             # CSRF state 생성/검증
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # /api/* 라우터
│   │   ├── searchconsole.py     # SearchConsoleClient (google-api-python-client 래퍼)
│   │   └── schemas.py           # Pydantic 요청/응답 모델
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py          # SQLite 연결 관리 + 테이블 생성
│   │   └── repository.py        # 사용자/세션/프로젝트/캐시 CRUD
│   │
│   └── core/
│       ├── __init__.py
│       ├── security.py          # Fernet 암복호화, 키 로딩
│       ├── session.py           # 쿠키 기반 세션 (서명 + 만료)
│       └── errors.py            # 표준 에러 응답
│
├── tests/
│   ├── conftest.py
│   ├── test_auth_flow.py        # OAuth 플로우 통합 테스트 (Mock Google endpoints)
│   ├── test_token_store.py      # 암호화/복호화 테스트
│   └── test_api_endpoints.py    # /api/* 테스트
│
└── scripts/
    ├── gen_key.py               # Fernet 키 생성 헬퍼
    └── local_ngrok.md           # 로컬 개발용 ngrok 가이드

# ─────────────────────────────────────────────
# 프론트엔드 (별도 패키지: frontend/)
# ─────────────────────────────────────────────
frontend/
├── package.json
├── vite.config.ts              # dev proxy → :8100, prod는 FastAPI에 정적 서빙
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── index.html
├── .env.example                # VITE_API_BASE_URL
├── src/
│   ├── main.tsx                # 엔트리, BrowserRouter, QueryClientProvider
│   ├── App.tsx                 # 라우터 정의 + AuthGuard
│   │
│   ├── api/                    # 백엔드 API 클라이언트 (fetch wrapper)
│   │   ├── client.ts           # credentials:'include' 기본
│   │   ├── auth.ts             # /auth/status, /auth/logout
│   │   ├── sites.ts            # /api/sites
│   │   ├── analytics.ts        # /api/searchanalytics/query
│   │   └── sitemaps.ts         # /api/sitemaps
│   │
│   ├── auth/                   # 인증 컨텍스트 + 가드
│   │   ├── AuthContext.tsx     # 세션 상태, isAuthenticated
│   │   ├── useAuth.ts
│   │   └── AuthGuard.tsx       # 비로그인 시 /login 리다이렉트
│   │
│   ├── routes/                 # 페이지 컴포넌트
│   │   ├── LoginPage.tsx       # "Google로 로그인" 버튼
│   │   ├── CallbackPage.tsx    # (선택) OAuth 콜백 처리 (백엔드 콜백 후 SPA 리다이렉트면 불필요)
│   │   ├── SitesPage.tsx       # 사이트 선택 화면
│   │   └── DashboardPage.tsx   # 선택된 사이트 대시보드
│   │
│   ├── features/
│   │   ├── overview/           # 상단 요약 카드 (총 클릭/노출/CTR/평균 위치)
│   │   │   ├── KpiCards.tsx
│   │   │   └── TrendChart.tsx
│   │   ├── queries/            # 상위 검색어 테이블 + 필터
│   │   ├── pages/              # 상위 페이지 테이블
│   │   ├── countries/          # 국가별 트래픽
│   │   ├── devices/            # 디바이스 분포
│   │   └── sitemaps/           # 사이트맵 상태
│   │
│   ├── components/             # 공용 UI (shadcn/ui 베이스)
│   │   ├── ui/                 # button, card, dialog, table ...
│   │   ├── DateRangePicker.tsx
│   │   ├── SiteSelector.tsx
│   │   └── EmptyState.tsx
│   │
│   ├── lib/                    # 유틸
│   │   ├── format.ts           # 숫자/퍼센트/날짜 포맷
│   │   └── queryKeys.ts        # React Query 키 일원화
│   │
│   └── styles/
│       └── globals.css
│
└── tests/
    ├── unit/                   # Vitest
    └── e2e/                    # Playwright (로그인→사이트 선택→대시보드)
```
```

---

## 5. OAuth 2.0 인증 플로우 (상세)

### 5.1 Scope (Read-only)

```
https://www.googleapis.com/auth/webmasters.readonly
```

> **쓰기 권한(`webmasters`)** 은 사용하지 않는다. 향후 필요 시 별도 옵션으로 확장하되, 현재 plan은 **읽기 전용**만 다룬다.

### 5.2 Step 1 — `/auth/login` (사용자 → Google로 리다이렉트)

엔드포인트: `GET /auth/login`

1. 서버는 `state`(CSRF 토큰) 생성 → 서버사이드 세션(또는 서명 쿠키)에 저장.
2. Google OAuth URL 생성:
   ```
   https://accounts.google.com/o/oauth2/v2/auth?
     client_id=YOUR_CLIENT_ID
     &redirect_uri=http://localhost:8100/auth/callback
     &response_type=code
     &scope=https://www.googleapis.com/auth/webmasters.readonly
     &access_type=offline
     &prompt=consent
     &include_granted_scopes=true
     &state=<RANDOM_STATE>
   ```
3. `302` 응답으로 브라우저 리다이렉트.

**핵심 옵션**
- `access_type=offline` → **refresh_token** 발급 (1회만 발급되므로 `prompt=consent` 필수).
- `prompt=consent` → 매번 동의 화면 강제 표시 (refresh_token 재발급 보장).
- `include_granted_scopes=true` → 증분 권한 요청.

### 5.3 Step 2 — `/auth/callback` (Google → 백엔드)

엔드포인트: `GET /auth/callback?code=...&state=...&scope=...`

처리 로직:
1. `state` 검증 (세션과 일치 확인) → 불일치 시 **400**.
2. `code` 추출 → 없으면 **400**.
3. POST `https://oauth2.googleapis.com/token` (application/x-www-form-urlencoded):
   ```
   code=<AUTH_CODE>
   client_id=<CLIENT_ID>
   client_secret=<CLIENT_SECRET>
   redirect_uri=<REDIRECT_URI>
   grant_type=authorization_code
   ```
4. 응답(JSON):
   ```json
   {
     "access_token": "ya29...",
     "expires_in": 3599,
     "refresh_token": "1//0eX...",
     "scope": "https://www.googleapis.com/auth/webmasters.readonly",
     "token_type": "Bearer"
   }
   ```
5. `access_token` 만료 시각(`now + expires_in - 60s`) 계산.
6. 토큰 페이로드(아래 §6) **암호화** 후 Token Store 저장.
7. 세션 쿠키 발급 → `302 /` 또는 프론트엔드 대시보드로 리다이렉트.

### 5.4 Step 3 — `/auth/status`, `/auth/logout`

- `GET /auth/status` → `{ "authenticated": true, "scopes": [...] }` 또는 `false`.
- `POST /auth/logout` → Token Store에서 해당 세션 삭제 + 쿠키 만료.

### 5.5 Step 4 — 자동 Refresh

매 API 호출 시:
1. Token Store에서 토큰 로드 → **복호화**.
2. `access_token` 만료 임박(예: 60초 이내) 또는 API 호출이 **401**을 반환하면:
   - POST `https://oauth2.googleapis.com/token` (grant_type=refresh_token)
     ```
     refresh_token=<REFRESH>
     client_id=<CLIENT_ID>
     client_secret=<CLIENT_SECRET>
     grant_type=refresh_token
     ```
   - 새 `access_token` 수신 → **재암호화** 후 저장.
3. 갱신된 `access_token`으로 원래 요청 재시도.

> Google 응답에 `refresh_token`이 다시 안 올 수 있다(이미 발급된 경우). **기존 refresh_token을 유지**하면서 `access_token`만 교체한다.

---

## 6. 토큰 저장 전략 (Token Store)

### 6.1 저장소 선택 (단계별)

| 단계 | 저장소 | 적합 시점 |
|------|--------|----------|
| **현재** | **MariaDB (asyncmy)** — 운영 환경 | `config.toml`에서 `use_sqlite = false` |
| 개발/테스트 | **SQLite (aiosqlite)** — 로컬 개발 및 pytest | `config.toml`에서 `use_sqlite = true` |
| Prod | PostgreSQL (또는 Redis + DB) | 멀티 인스턴스 배포 |

> **2026-08-03 업데이트**: SQLite 단일 저장소에서 **MariaDB + SQLite 듀얼 백엔드**로 업그레이드. `Database` 래퍼 클래스가 SQLite SQL(`?`, `ON CONFLICT`)을 MySQL SQL(`%s`, `ON DUPLICATE KEY UPDATE`)로 자동 변환한다. DB 연결 정보는 `config.toml`로 분리.

### 6.2 데이터베이스 스키마 (MariaDB)

> 운영 DB: `<DB_HOST>:3306/google` (InnoDB, utf8mb4)

#### ER 다이어그램

```
┌──────────┐         ┌───────────┐         ┌──────────────────┐
│  users   │ 1───┬──N │  sessions │         │  analytics_cache │
│          │     │    │           │         │                  │
│ user_id  │◀────┼────│ user_id   │         │ id (PK)          │
│ email    │     │    │ session_id│         │ project_id (FK)  │──┐
│ created_ │     │    │ email     │         │ query_hash       │  │
│   at     │     │    │ scopes    │         │ data_json (JSON) │  │
└──────────┘     │    │ access_   │         │ fetched_at       │  │
                 │    │  token_   │         │ expires_at       │  │
                 │    │  cipher   │         └──────────────────┘  │
                 │    │ refresh_  │                                │
                 │    │  token_   │         ┌──────────────────┐  │
                 │    │  cipher   │         │ sitemaps_cache   │  │
                 │    │ expires_  │         │                  │  │
                 │    │  at       │         │ id (PK)          │  │
                 │    │ created_  │         │ project_id (FK)  │──┤
                 │    │  at       │         │ data_json (JSON) │  │
                 │    │ updated_  │         │ fetched_at       │  │
                 │    │  at       │         │ expires_at       │  │
                 │    └───────────┘         └──────────────────┘  │
                 │                                                │
                 │    ┌───────────┐                               │
                 └──N │ projects  │ 1─────────────────────────────┘
                      │           │
                      │ id (PK)   │
                      │ user_id ◀─┼── FK → users.user_id
                      │ site_url  │
                      │ permission│
                      │ _level    │
                      │ created_  │
                      │  at       │
                      └───────────┘
```

#### 테이블 상세

**users** — Google 사용자 계정
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `user_id` | `VARCHAR(255)` PK | Google OAuth `sub` |
| `email` | `VARCHAR(255)` NOT NULL | Google 계정 이메일 |
| `created_at` | `DOUBLE` | 최초 로그인 시각 (unix timestamp) |

**sessions** — OAuth 토큰 저장소 (Fernet 암호화)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `session_id` | `VARCHAR(64)` PK | UUID 기반 세션 식별자 |
| `user_id` | `VARCHAR(255)` FK → users | 소유자 |
| `email` | `VARCHAR(255)` | 중복 저장 (빠른 조회용) |
| `scopes` | `TEXT` | JSON 배열 |
| `access_token_ciphertext` | `TEXT` | Fernet 암호화된 access token |
| `refresh_token_ciphertext` | `TEXT` | Fernet 암호화된 refresh token |
| `access_token_expires_at` | `DOUBLE` | 토큰 만료 시각 |
| `created_at` | `DOUBLE` | 세션 생성 시각 |
| `updated_at` | `DOUBLE` | 마지막 갱신 시각 |

**projects** — Search Console 사이트
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | `INT` PK AUTO_INCREMENT | 내부 프로젝트 ID |
| `user_id` | `VARCHAR(255)` FK → users | 소유자 |
| `site_url` | `TEXT` | 사이트 URL |
| `permission_level` | `VARCHAR(50)` | siteOwner / siteFullUser / siteRestrictedUser |
| `created_at` | `DOUBLE` | 등록 시각 |

**analytics_cache** — Search Analytics API 캐시 (TTL: 6시간)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | `INT` PK AUTO_INCREMENT | 내부 ID |
| `project_id` | `INT` FK → projects | 대상 프로젝트 |
| `query_hash` | `VARCHAR(64)` | SHA256(startDate, endDate, dimensions, rowLimit) |
| `data_json` | `LONGTEXT` | GSC API 응답 원본 (JSON) |
| `fetched_at` | `DOUBLE` | 캐시 저장 시각 |
| `expires_at` | `DOUBLE` | 캐시 만료 시각 |

**sitemaps_cache** — Sitemaps API 캐시 (TTL: 24시간)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | `INT` PK AUTO_INCREMENT | 내부 ID |
| `project_id` | `INT` FK → projects | 대상 프로젝트 |
| `data_json` | `LONGTEXT` | GSC API 응답 원본 (JSON) |
| `fetched_at` | `DOUBLE` | 캐시 저장 시각 |
| `expires_at` | `DOUBLE` | 캐시 만료 시각 |

#### 인덱스

| 인덱스 | 테이블 | 목적 |
|--------|--------|------|
| `idx_projects_user` | `projects(user_id)` | 사용자별 사이트 조회 |
| `idx_analytics_cache_project` | `analytics_cache(project_id)` | 프로젝트별 캐시 조회 |
| `idx_sitemaps_cache_project` | `sitemaps_cache(project_id)` | 프로젝트별 사이트맵 조회 |
| `idx_sessions_user` | `sessions(user_id)` | 사용자별 세션 조회 |

### 6.3 DB 설정 (config.toml)

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

> 실제 접속 정보는 저장소에 커밋하지 않고 로컬 `config.toml`(gitignore 대상)에서 관리한다.

- `app/config.py`의 `DatabaseConfig`가 `config.toml`을 파싱
- `Database` 래퍼가 SQLite ↔ MySQL 방언 자동 변환 (`?`↔`%s`, `ON CONFLICT`↔`ON DUPLICATE KEY UPDATE`)
- pytest 실행 시 `conftest.py`가 임시 `config.toml`을 생성하여 `use_sqlite = true` 강제

### 6.4 세션 ↔ 토큰 매핑

- **서버사이드 세션**: `session_id` → 토큰 레코드. 쿠키에는 서명된 `session_id`만 노출.
- **쿠키 속성**: `HttpOnly`, `Secure`(prod), `SameSite=Lax`, `Path=/`, `Max-Age=30d`.

---

## 7. API 엔드포인트 명세 (Read-only)

> 모든 `/api/*` 엔드포인트는 인증 필요 (`deps.py`에서 `session_id` 검증).

### 7.1 `GET /api/sites`

Search Console에 등록된 사이트 목록.

- 백엔드 호출: `GET https://www.googleapis.com/webmasters/v3/sites`
- 응답 (예시):
  ```json
  {
    "siteEntry": [
      { "siteUrl": "https://example.com/", "permissionLevel": "siteOwner" },
      { "siteUrl": "https://example.com/", "permissionLevel": "siteFullUser" }
    ]
  }
  ```

### 7.2 `POST /api/searchanalytics/query`

검색 트래픽 분석.

- 요청 바디:
  ```json
  {
    "siteUrl": "https://example.com/",
    "startDate": "2026-06-01",
    "endDate": "2026-06-30",
    "dimensions": ["query", "page"],
    "rowLimit": 10,
    "dimensionFilterGroups": [...]
  }
  ```
- 백엔드 호출: `POST https://www.googleapis.com/webmasters/v3/sites/{siteUrl}/searchAnalytics/query`
- 응답: GSC 원본 그대로 매핑 (또는 우리 스키마로 정규화).

### 7.3 `GET /api/sitemaps?siteUrl=...`

- 백엔드 호출: `GET https://www.googleapis.com/webmasters/v3/sites/{siteUrl}/sitemaps`

### 7.4 `GET /api/urlinspection/index`

- 백엔드 호출: `POST https://searchconsole.googleapis.com/v1/urlInspection/index:inspect`
- URL Inspection API는 별도 활성화 필요 (Cloud Console).

### 7.5 공통 에러 응답

```json
{
  "error": {
    "code": "GSC_UNAUTHORIZED",
    "message": "Access token expired and refresh failed",
    "detail": { "status": 401 }
  }
}
```

| 코드 | HTTP | 의미 |
|------|------|------|
| `UNAUTHENTICATED` | 401 | 세션 없음/만료 → `/auth/login`으로 유도 |
| `TOKEN_REFRESH_FAILED` | 401 | refresh_token도 만료 → 재로그인 필요 |
| `INSUFFICIENT_SCOPE` | 403 | read-only 외 요청 차단 |
| `RATE_LIMITED` | 429 | 백오프 후 재시도 (헤더 `Retry-After` 존중) |
| `UPSTREAM_ERROR` | 502 | GSC API 오류 |

---

## 8. 프론트엔드 아키텍처 (React + Vite SPA)

> **목적**: 사용자가 처음 보게 될 화면(= "처음 보이는 화면")을 포함해, 인증 → 사이트 선택 → 대시보드까지의 UX와 라우팅·상태·API 연동을 정의한다. **백엔드는 `/api/*` + `/auth/*` 만 담당**하고, 화면 렌더링은 전부 SPA에서 처리한다.

### 8.1 사용자 여정 (User Journey)

```
[로그인 전]              [로그인 후 - 1단계]              [2단계]                    [3단계]
┌────────────┐         ┌────────────────────┐        ┌──────────────────┐      ┌──────────────────┐
│ /login     │ ──▶ ──▶ │  / (SitesPage)     │ ──▶──▶ │ /dashboard       │      │ /dashboard       │
│ "Google로  │  OAuth  │  등록된 사이트 목록 │  클릭  │ /:siteUrl        │      │ (필터/탐색)      │
│  로그인"   │  콜백   │  + 권한 수준 표시   │        │ (기본 90일 분석)  │      │                  │
└────────────┘         └────────────────────┘        └──────────────────┘      └──────────────────┘
```

- **/login** : 진입점. Google OAuth 버튼 하나. 클릭 → `window.location.href = "/auth/login"` (백엔드 → Google → 콜백 → 쿠키 발급 → SPA로 다시 리다이렉트).
- **/sites** : 인증 후 처음 보이는 화면. 사용자의 GSC에 등록된 모든 사이트 카드 + 권한(`siteOwner`/`siteFullUser`/`siteRestrictedUser`) 표시. 하나 선택 시 다음 단계.
- **/dashboard/:siteUrl** : 선택한 사이트의 분석 화면. 기본 날짜 범위 = 최근 90일.
- **/dashboard (필터 모드)** : 날짜·디멘전·필터 변경 → URL 쿼리(`?start=&end=&dim=`) 동기화 → React Query 캐시 키로 반영.

> **선택 사이트 영속화**: 마지막으로 본 사이트는 `localStorage("lastSiteUrl")`에 저장 → 재방문 시 `SitesPage`를 건너뛰고 곧바로 대시보드 진입 (선택 사항).

### 8.2 라우트 트리

| 경로 | 컴포넌트 | 가드 | 비고 |
|------|---------|------|------|
| `/login` | `LoginPage` | 공개 | OAuth 버튼 |
| `/auth/callback` | (백엔드 핸들러) | - | SPA 진입 X, 302로 `/sites`로 리다이렉트 |
| `/` | `SitesPage` | `AuthGuard` | 미인증 → `/login` |
| `/dashboard` | `DashboardRedirect` | `AuthGuard` | `lastSiteUrl` 있으면 `:siteUrl`로 리다이렉트 |
| `/dashboard/:siteUrl` | `DashboardPage` | `AuthGuard` + `SiteOwnerCheck` | 미등록 사이트면 `/`로 |
| `*` | `NotFound` | - | 404 |

### 8.3 인증 상태 관리

```typescript
// filepath: frontend/src/auth/AuthContext.tsx (요지)
type AuthState = {
  isAuthenticated: boolean;
  isLoading: boolean;     // /auth/status 폴링/체크 중
  email?: string;
  scopes?: string[];
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState>(...);

export function AuthProvider({ children }) {
  const [state, setState] = useState<AuthState>({ isAuthenticated: false, isLoading: true, ... });

  useEffect(() => {
    api.get('/auth/status')
      .then(r => setState({ isAuthenticated: true, isLoading: false, ...r }))
      .catch(() => setState({ isAuthenticated: false, isLoading: false }));
  }, []);

  const logout = async () => {
    await api.post('/auth/logout');
    setState({ isAuthenticated: false, isLoading: false });
    location.href = '/login';
  };

  return <AuthContext.Provider value={...}>{children}</AuthContext.Provider>;
}
```

- **세션 확인**: 페이지 첫 로드 시 `GET /auth/status` 1회 호출 → 쿠키의 `session_id`가 살아있으면 OK, 없으면 `isAuthenticated=false`.
- **`AuthGuard`** : 라우트 진입 시 `isLoading` 끝날 때까지 스피너 → `false`면 `/login` 리다이렉트.
- **자동 재검증**: React Query의 `staleTime` + `refetchOnWindowFocus`로 토큰 만료 시 백엔드에서 401 → 인터셉터가 `/auth/status` 재호출 → 실패 시 `/login`으로 보냄.

### 8.4 "처음 보이는 화면" 상세 명세

#### 8.4.1 `/login` (LoginPage)

- **UI**:
  - 로고 + 제품명 ("Google Search Console Dashboard")
  - Google 로고가 들어간 단일 버튼: **"Google 계정으로 로그인"**
  - 하단 안내: "로그인하면 Google Search Console의 데이터(읽기 전용)에 접근합니다."
- **동작**: 버튼 클릭 → `window.location.href = '/auth/login'` (백엔드 라우트가 Google로 302). 백엔드가 콜백을 모두 처리한 후 SPA의 `/` (SitesPage)로 다시 리다이렉트.
- **에러**: `/auth/callback?error=...` 로 들어온 경우 (`access_denied` 등) → 에러 메시지 + 재시도 버튼.

#### 8.4.2 `/sites` (SitesPage) — 인증 후 첫 화면

> **이 화면이 "처음 보이는 화면"의 본체.**

- **헤더**: 좌측 로고, 우측 사용자 이메일 + 드롭다운(`로그아웃`).
- **메인**: 페이지 타이틀 "내 Search Console 사이트"
  - **로딩 상태**: 스켈레톤 카드 4~6개
  - **데이터 있음**: 그리드(반응형 1~3열)로 사이트 카드 표시
    - 카드 내용: 사이트 URL (`https://example.com/`), **권한 레벨 뱃지** (`siteOwner` = 파란색, `siteFullUser` = 초록, `siteRestrictedUser` = 회색), 마지막 크롤링/오류 알림(선택)
    - 카드 클릭 → `/dashboard/{encodeURIComponent(siteUrl)}` 이동
  - **데이터 없음 (빈 상태)**: 일러스트 + "Search Console에 등록된 사이트가 없습니다. [Search Console 열기]" 외부 링크
  - **에러 상태**: "사이트 목록을 불러올 수 없습니다. [다시 시도]" 버튼
- **API**: `GET /api/sites` → React Query (`queryKey: ['sites']`, `staleTime: 5min`)

#### 8.4.3 `/dashboard/:siteUrl` (DashboardPage)

- **상단 바**:
  - `SiteSelector` (현재 사이트 변경 → 다른 사이트 페이지로 이동)
  - `DateRangePicker` (프리셋: 7일/28일/90일/6개월 + 커스텀, 기본 90일)
  - 디멘전 토글 (Query / Page / Country / Device / Date / Search Appearance)
  - `내보내기(CSV)` 버튼 (선택)
- **본문 - Overview 카드 4개**:
  - 총 **클릭수** (전 기간 대비 증감률)
  - 총 **노출수** (증감률)
  - 평균 **CTR** (%)
  - 평균 **순위** (Position)
- **차트 영역**:
  - 일별 클릭/노출 트렌드 라인 차트 (Recharts)
  - 디멘전별 토픽 차트 (스택 바 / 테이블)
- **테이블 영역**:
  - 상위 검색어 (clicks DESC, 25행, 정렬·페이지네이션)
  - 상위 페이지
  - 국가/디바이스 분포
- **데이터 호출**:
  - 한 번에 한 쿼리(`/api/searchanalytics/query`)에 디멘전 1~2개씩 묶어 호출
  - React Query로 디멘전별 캐시 (`queryKey: ['analytics', siteUrl, start, end, dim]`)
  - 차트 데이터: `dimensions: ['date']`, 테이블: `dimensions: ['query']` 등
- **빈 상태**: 데이터 0건 → "선택한 기간에 검색 트래픽이 없습니다."

### 8.5 컴포넌트 트리 (요약)

```
<App>
└── <AuthProvider>
    └── <QueryClientProvider>
        └── <Router>
            ├── /login        → <LoginPage/>
            ├── /             → <AuthGuard><SitesPage/></AuthGuard>
            ├── /dashboard    → <AuthGuard><DashboardRedirect/></AuthGuard>
            └── /dashboard/:siteUrl
                             → <AuthGuard>
                               <DashboardShell>
                                 <SiteHeader>
                                   <SiteSelector/> <DateRangePicker/> <DimensionToggle/> <ExportButton/>
                                 </SiteHeader>
                                 <KpiCards/> <TrendChart/> <QueriesTable/> <PagesTable/> ...
                               </DashboardShell>
                             </AuthGuard>
```

### 8.6 Vite 개발 서버 ↔ FastAPI 연동

- **개발 (Vite dev server, `:5173`)**:
  - `vite.config.ts`에 `/auth` 및 `/api` 경로를 `:8100`으로 **프록시** + `changeOrigin: true` + `secure: false` + `cookieDomainRewrite: 'localhost'`.
  - → 브라우저는 `localhost:5173`만 보지만, 쿠키는 `localhost` 도메인 기준으로 발행되어 양쪽에서 공유됨.
- **운영 (단일 도메인)**:
  - FastAPI가 `/` (SPA 정적 파일) + `/auth/*` + `/api/*` 모두 서빙.
  - `vite build` 산출물(`frontend/dist/`)을 `app/static/`으로 복사 → FastAPI에서 `StaticFiles(html=True)`로 마운트, SPA fallback (`serve SPA`).
- **운영 (분리 도메인)**:
  - FastAPI에 `CORSMiddleware` + `allow_credentials=True` + `allowed_origins=["https://app.yourdomain.com"]`.
  - 프론트는 `VITE_API_BASE_URL=https://api.yourdomain.com` + 모든 fetch에 `credentials: 'include'`.
  - 쿠키: `Domain=.yourdomain.com`, `SameSite=None; Secure` (cross-site).

### 8.7 React Query 키/패턴 규약

```typescript
// filepath: frontend/src/lib/queryKeys.ts (요지)
export const qk = {
  authStatus: () => ['auth', 'status'] as const,
  sites:      () => ['sites'] as const,
  analytics:  (siteUrl: string, start: string, end: string, dim: string[]) =>
                ['analytics', siteUrl, start, end, dim] as const,
  sitemaps:   (siteUrl: string) => ['sitemaps', siteUrl] as const,
};
```

- **재검증 정책**:
  - `sites`: `staleTime: 5min` (권한은 자주 안 바뀜)
  - `analytics`: `staleTime: 10min` (GSC 데이터 자체가 보통 1~3일 지연)
  - 사이트 변경 시 `qk.analytics`를 `queryClient.removeQueries`로 무효화.
- **401 인터셉터**:
  ```typescript
  // filepath: frontend/src/api/client.ts (요지)
  async function fetchJson(input: RequestInfo, init?: RequestInit) {
    const res = await fetch(input, { credentials: 'include', ...init });
    if (res.status === 401) {
      // 토큰 만료 → 백엔드에서 자동 refresh 시도 후에도 실패한 경우
      window.location.href = '/login';
    }
    if (!res.ok) throw new ApiError(res);
    return res.json();
  }
  ```

### 8.8 라우트-레벨 데이터 로딩 (Suspense + Query)

- React Query는 Suspense 모드를 사용하지 않고, 각 페이지에서 `useQuery` + `isLoading/isError` 분기로 처리 (단순/디버깅 용이).
- 로딩 중에는 **스켈레톤 UI** (shadcn `Skeleton`) 사용 → CLS 방지.
- 대시보드 첫 진입 시 **병렬 호출**: `['date']` + `['query']` + `['page']` + `['device']` 등 4~5개 쿼리를 `Promise.all` 또는 React Query의 병렬 자동 fetch로 동시 요청.

### 8.9 환경 변수 (프론트)

```dotenv
# filepath: frontend/.env.example
VITE_API_BASE_URL=                 # 비워두면 same-origin (단일 도메인). 분리 시 https://api.yourdomain.com
VITE_APP_NAME=Google Search Console Dashboard
VITE_DEFAULT_DATE_RANGE_DAYS=90
```

### 8.10 접근성 / UX 가이드

- **a11y**: 모든 인터랙티브 요소는 키보드 포커스 가능, `aria-label` 제공, 색만으로 상태 전달 금지(아이콘·텍스트 병기).
- **반응형**: 데스크톱 우선(대시보드), 모바일은 카드 스택/스크롤. 테이블은 가로 스크롤.
- **다크 모드**: Tailwind `class` 전략 + `next-themes` 또는 자체 토글.
- **국제화**: 본 plan 범위는 한국어/영어. `i18next` + `react-i18next`로 분리.
- **에러 UX**: 모든 에러는 `Toast` + 재시도 CTA. 토큰 만료로 `/login` 보낼 때는 "세션이 만료되었습니다" 안내.

### 8.11 테스트 (Vitest + Playwright)

- **단위** (Vitest): `format.ts`, 쿼리 키 빌더, `AuthGuard` 분기.
- **컴포넌트** (Testing Library): `LoginPage` 버튼 클릭 → `/auth/login`으로 `window.location.href` 변경되는지, `SitesPage`에서 카드 클릭 시 라우터 push 발생.
- **E2E** (Playwright):
  1. `/login` → Google OAuth 모킹(또는 테스트 계정) → `/sites` 진입
  2. 사이트 카드 클릭 → 대시보드 진입
  3. `DateRangePicker` 변경 → 차트 데이터 갱신
  4. `로그아웃` → `/login`으로 이동
- **MSW (Mock Service Worker)**: 백엔드 `/api/*`를 모킹 → 단위/E2E 모두에서 오프라인 실행.

---

## 9. 핵심 모듈 스케치 (코드 윤곽)

> 본 섹션은 **인터페이스와 책임**만 정의한다. 실제 구현은 Phase별 로드맵(§13)에 따라 채운다.

### 9.1 `app/config.py`

```python
# filepath: app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_scopes: list[str] = ["https://www.googleapis.com/auth/webmasters.readonly"]

    token_encryption_key: str          # Fernet key (urlsafe base64)
    session_secret_key: str            # itsdangerous
    session_cookie_name: str = "gsc_session"
    session_max_age: int = 60 * 60 * 24 * 30

    token_store_path: str = ".tokens"
    allowed_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

settings = Settings()
```

### 9.2 `app/core/security.py`

- `get_fernet() -> Fernet`
- `encrypt_token(plain: str) -> str`
- `decrypt_token(cipher: str) -> str`

### 9.3 `app/auth/oauth.py`

```python
# filepath: app/auth/oauth.py (요지)
from google_auth_oauthlib.flow import Flow

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

def make_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
```

### 9.4 `app/auth/routes.py`

```python
# filepath: app/auth/routes.py (요지)
@router.get("/login")
def login(request: Request):
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state  # 또는 서명 쿠키
    flow = make_flow(settings.google_redirect_uri)
    url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true",
        prompt="consent", state=state,
    )
    return RedirectResponse(url)

@router.get("/callback")
def callback(request: Request, code: str, state: str):
    assert state == request.session.pop("oauth_state")  # CSRF
    flow = make_flow(settings.google_redirect_uri)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    # ... 사용자 정보 조회(people/me 또는 userinfo) → email/user_id 추출
    # ... token_store.save(...)
    # ... 세션 쿠키 발급
    return RedirectResponse("/")
```

### 9.5 `app/api/searchconsole.py`

- `SearchConsoleClient(credentials: Credentials)`
  - `list_sites() -> list[SiteEntry]`
  - `query(site_url, body) -> list[Row]`
  - `list_sitemaps(site_url) -> list[Sitemap]`
  - `inspect_url(site_url, url) -> InspectionResult`

- 내부적으로 `httpx.AsyncClient` 또는 `google-api-python-client` 중 선택. 인터페이스를 통일해 교체 용이.

### 9.6 `app/deps.py`

```python
# filepath: app/deps.py (요지)
def current_session(request: Request) -> SessionRecord:
    sid = request.cookies.get(settings.session_cookie_name)
    if not sid: raise HTTPException(401, "UNAUTHENTICATED")
    rec = token_store.load(sid)
    if not rec: raise HTTPException(401, "UNAUTHENTICATED")
    return rec

def gsc_client(session: SessionRecord = Depends(current_session)) -> SearchConsoleClient:
    creds = token_store.materialize_credentials(session)  # 필요 시 refresh
    return SearchConsoleClient(creds)
```

---

## 10. 보안 체크리스트

| 항목 | 적용 |
|------|------|
| HTTPS (prod) | 필수. 로컬은 http://localhost 허용. |
| `state` 파라미터 | OAuth login/callback에 사용, 서버사이드 세션에 저장. |
| PKCE | 공개 클라이언트가 아니므로 **선택**. 추후 모바일/데스크톱 클라이언트 추가 시 적용. |
| `Secure`, `HttpOnly`, `SameSite=Lax` 쿠키 | prod에서 모두 적용. |
| 토큰 at-rest 암호화 | Fernet (AES-128 + HMAC-SHA256). |
| 토큰 로그 마스킹 | `****`로 마스킹 후 출력. |
| 최소 Scope | `webmasters.readonly`만 요청. |
| 입력 검증 | Pydantic 스키마로 화이트리스트 검증 (날짜, dimension 등). |
| Rate Limit | Upstream 429 시 `Retry-After` 존중, 지수 백오프. |
| Refresh Token 회전 | Google 정책상 자동. 손상 감지 시 revoke + 재로그인 안내. |
| CORS | 프론트엔드 origin 화이트리스트. |
| CSRF (state 외) | mutating API에 CSRF 토큰 또는 `SameSite=Strict`로 방어. |
| 비밀 관리 | `.env`는 git 제외, 시크릿 매니저(Vault/AWS SM/GCP SM) 사용. |

---

## 11. 환경 변수 (`.env.example`)

```dotenv
# Google OAuth
GOOGLE_CLIENT_ID=xxxxxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx
GOOGLE_REDIRECT_URI=http://localhost:8100/auth/callback
# comma-separated, 기본값은 read-only
GOOGLE_SCOPES=https://www.googleapis.com/auth/webmasters.readonly

# 보안 키 (운영 시 시크릿 매니저에서 주입)
TOKEN_ENCRYPTION_KEY= # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SESSION_SECRET_KEY=   # python -c "import secrets; print(secrets.token_urlsafe(32))"

# 저장소
TOKEN_STORE_PATH=.tokens
SESSION_COOKIE_NAME=gsc_session
SESSION_MAX_AGE=2592000

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## 12. 단계별 구현 로드맵

### Phase 0 — Google Cloud 설정 (수동, 30분)
- [ ] 프로젝트 생성
- [ ] Search Console API 활성화
- [ ] OAuth 동의 화면 구성 (External, Testing 모드 + 본인 계정 추가)
- [ ] OAuth Client ID/Secret 발급, redirect URI 등록
- [ ] 발급된 키를 안전한 곳에 보관

### Phase 1 — 프로젝트 골격 (1~2시간)
- [ ] `uv`로 의존성 추가 (`fastapi`, `uvicorn`, `pydantic-settings`, `google-auth-oauthlib`, `google-api-python-client`, `cryptography`, `itsdangerous`, `httpx`)
- [ ] `app/config.py`, `app/main.py`(헬스 체크 `/healthz`) 작성
- [ ] `.env.example`, `.gitignore` 작성
- [ ] `scripts/gen_key.py`로 Fernet 키 생성

### Phase 2 — OAuth 플로우 (2~3시간)
- [ ] `app/auth/oauth.py`: `Flow` 팩토리
- [ ] `app/auth/state.py`: state 생성/검증
- [ ] `app/auth/routes.py`: `/auth/login`, `/auth/callback`
- [ ] `userinfo` 호출로 `email`, `user_id` 확보
- [ ] 로컬에서 end-to-end 수동 테스트 (브라우저 → 콜백 → 토큰 확인)

### Phase 3 — 토큰 저장 (1~2시간)
- [ ] `app/core/security.py`: Fernet 헬퍼
- [ ] `app/auth/token_store.py`: 파일 기반 저장 (세션 ID별 JSON)
- [ ] `app/core/session.py`: 서명 쿠키 발급/검증
- [ ] `/auth/status`, `/auth/logout` 구현

### Phase 4 — Search Console 클라이언트 (2~3시간)
- [ ] `SearchConsoleClient` 인터페이스 정의
- [ ] `google-api-python-client` 기반 구현체 + 단위 테스트
- [ ] `httpx` 기반 구현체 (교체 가능하도록)
- [ ] 자동 refresh 로직 + 재시도(지수 백오프)

### Phase 5 — REST API 라우터 (1~2시간)
- [ ] `app/api/schemas.py`: 요청/응답 모델
- [ ] `app/api/routes.py`: `/api/sites`, `/api/searchanalytics/query`, `/api/sitemaps`
- [ ] `app/deps.py`: 세션/토큰 의존성
- [ ] `app/core/errors.py`: 표준 에러 변환

### Phase 6 — 통합 테스트 (2~3시간)
- [ ] `httpx.MockTransport`로 Google endpoints 모킹
- [ ] OAuth 플로우 통합 테스트
- [ ] 토큰 refresh 시나리오 테스트
- [ ] `/api/*` 응답 스키마 테스트

### Phase 7 — 배포 준비 (1~2시간)
- [ ] Dockerfile (멀티스테이지, non-root)
- [ ] docker-compose (Postgres 옵션)
- [ ] GitHub Actions: ruff/mypy/pytest
- [ ] `README.md`에 셋업/실행/배포 가이드
- [ ] 운영 redirect URI 추가, prod 환경변수 등록
- [ ] (선택) Google 앱 검증 신청 자료 준비

---

## 13. 향후 확장 아이디어 (본 plan 범위 외)

- **프론트엔드 대시보드**: React/Vite + Chart.js/Recharts. 토큰은 백엔드 세션만 사용.
- **멀티 유저**: User 테이블, OAuth state를 DB에 저장, 동시 로그인 격리.
- **캐싱 레이어**: 검색 분석 결과 TTL 기반 캐시 (예: Redis 1h), 사용자/사이트/쿼리 키.
- **Rate Limit 가드**: 사용자별 토큰 버킷.
- **감사 로그**: API 호출 이력 (사용자, 엔드포인트, 시각, 지표).
- **Background sync**: 주기적으로 GSC 데이터 → 사내 DB 적재 → 자체 분석.
- **URL Inspection API 추가**: 색인 상태/모바일 친화성 점검.
- **Apps Script / Sheets Export**: 한 번에 엑셀로 내보내기.

---

## 14. 결정 요약 (Decisions)

| 결정 | 선택 | 이유 |
|------|------|------|
| OAuth Flow | Authorization Code (서버 사이드) | 표준, 안전, refresh_token 발급 |
| Scope | `webmasters.readonly` | 요구사항 |
| 토큰 저장 | Fernet 암호화 + JSON 파일 (MVP) → DB | 단순함에서 출발, 확장 가능 |
| 세션 | 서명 쿠키 + 서버사이드 토큰 매핑 | 로그아웃/무효화 용이 |
| 프레임워크 | FastAPI | 비동기, OpenAPI, 검증 |
| 클라이언트 | 추상화 + google-api-python-client(기본) | 호환성, 교체 용이 |
| 프론트엔드 | React 18 + Vite + TypeScript SPA | 백엔드와 분리, 모던/확장성 |
| 프론트 배포 | **단일 도메인**(FastAPI가 정적 SPA 서빙) | 운영 단순화, 쿠키 이슈 없음 |
| 라우팅 | React Router v6 (`/login`, `/`, `/dashboard/:siteUrl`) | 3단계 점진적 UX |
| 서버 상태 | TanStack Query | 캐싱/재검증/병렬 호출 |
| UI | TailwindCSS + shadcn/ui | 대시보드 조립 속도 |
| 차트 | Recharts | 검색 트래픽 시각화 |
| OAuth 진입 UX | `/login` → `GET /auth/login`(백엔드) → Google → 콜백 → SPA로 302 | 백엔드가 OAuth를 모두 처리, SPA는 버튼만 |
| 인증 후 첫 화면 | `/`(SitesPage) → 사이트 카드 → `/dashboard/:siteUrl` | 멀티 사이트 운영에 자연스러움 |

---

## 15. 참고 자료

- Google OAuth 2.0 Web Server Flow: <https://developers.google.com/identity/protocols/oauth2/web-server>
- Search Console API: <https://developers.google.com/webmaster-tools/search-console-api-original/v3>
- `google-auth-oauthlib`: <https://google-auth-oauthlib.readthedocs.io/>
- `google-api-python-client`: <https://github.com/googleapis/google-api-python-client>
- FastAPI: <https://fastapi.tiangolo.com/>
- Pydantic Settings: <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- cryptography (Fernet): <https://cryptography.io/en/latest/fernet/>

---

_본 plan은 초기 설계안이며, Phase별 구현 진행 시 구체적 인터페이스/스키마는 PR 단위로 갱신한다._
