# webstack

> 브랜드 정체성 기반 풀스택 스캐폴딩 + 컨트랙트 우선 API + 무료 티어 인프라 — Claude Code 플러그인.

`webstack`은 다음과 같은 구조화된 풀스택 빌드 사이클을 안내합니다:

1. **브랜드 정체성 & 페르소나 인터뷰** — 서비스가 추구하는 가치와 대상 사용자를 정리합니다.
2. **디자인 시스템 추출** — 정체성 + 페르소나에서 토큰, ShadCN 테마, 컴포넌트 변형을 도출합니다 (Refactoring UI 원칙).
3. **멀티 레포 스캐폴딩** — `<project>-frontend/` (Next.js + ShadCN + Tailwind v4), `<project>-backend/` (Spring Boot 4 + Kotlin + DDD/Hexagonal + KoTest BehaviorSpec), `<project>-infrastructure/` (OpenTofu)를 생성합니다.
4. **병렬 피처 개발** — 피처마다 git 워크트리로 격리, OpenAPI 3.1 컨트랙트 우선, BE/FE Implementer SubAgent 병렬 실행.
5. **무료 티어 배포** — Vercel + Oracle Cloud Always Free + Supabase + OpenTofu IaC.

## 설치

```text
# 1. 마켓플레이스 추가 (최초 1회):
/plugin marketplace add https://github.com/cares0/webstack

# 2. 플러그인 설치:
/plugin install webstack@webstack-marketplace
```

마켓플레이스 이름은 `webstack-marketplace` (`.claude-plugin/marketplace.json`에 선언), 플러그인 이름은 `webstack`입니다. 로컬 개발용이면 GitHub URL 대신 로컬 경로를 `marketplace add`에 전달하세요. Claude Code 플러그인 스펙상 `marketplace add` 후에야 `plugin install`이 동작합니다.

> 영어 원본: [README.md](README.md)

## 빠른 시작

```
cd <비어 있는 부모 디렉토리>
/webstack:init             # 1회 — 정체성 → 디자인 시스템 → 3개 레포 + SETUP.md
# SETUP.md에 따라 Vercel/Oracle/Supabase 가입, .env 채우고 export
/webstack:infra            # 1회 — tofu plan → 확인 → apply

# 피처마다
/webstack:feature <이름>    # 플랜 → 컨트랙트 → BE/FE 병렬 → 테스트 → 리뷰 → PR

# 배포할 때
/webstack:deploy           # FE는 push로 자동, BE는 SCP + systemd
```

## 생성되는 산출물

프로젝트마다 부모 디렉토리에 `.webstack/`이 생성됩니다:

```
.webstack/
├── manifest.yaml              프로젝트 메타데이터
├── identity.md                브랜드 아키타입 + 톤
├── personas/primary.md        Cooper 형식 페르소나
├── design-system/             tokens.json + theme.css + component-variants.md
├── contracts/<feature>.yaml   피처별 OpenAPI 3.1
├── features/<feature>/        플랜 + 상태 + 워크트리 경로
└── SETUP.md                   인프라 가입 가이드
```

3개의 형제 git 레포가 init에 의해 만들어집니다:

- `<project>-frontend/` — Next.js App Router + ShadCN + Tailwind v4 + RHF/Zod + TanStack Query.
- `<project>-backend/` — Spring Boot 4 + Kotlin + DDD/Hexagonal + KoTest BehaviorSpec + Spring Modulith + Flyway.
- `<project>-infrastructure/` — OpenTofu + vercel/vercel + oracle/oci + supabase/supabase 프로바이더.

## 전문화된 SubAgent

- `feature-architect` — 플랜 후 도메인/라우트 매핑.
- `backend-implementer` / `frontend-implementer` — 워크트리 안에서 병렬 구현.
- `code-reviewer` — DDD/RSC/Clean Code 리뷰.
- `contract-drift-detective` — springdoc과 OpenAPI YAML 비교.
- `test-runner` — KoTest + Vitest + Playwright.
- `tofu-plan-analyzer` — plan 출력 분류 + 위험도 + 무료 티어 영향.
- `security-auditor` — 시크릿 위생 + deny 규칙 + skip-permissions 검사.
- `design-system-architect` — 정체성/페르소나에서 토큰 + 변형 도출.
- `brand-archetype-matcher` — Jung 12 아키타입 점수화.

## 보안 모델

- AI는 `.env*` 파일을 절대 읽지 못합니다 (deny 규칙 + PreToolUse 훅).
- 토큰은 사용자 셸 환경변수에 두고 OpenTofu가 읽습니다. AI는 값을 보지 못합니다.
- OpenTofu의 민감 변수는 모두 `sensitive = true`로 마킹됩니다.
- 모든 파괴적 작업(apply/destroy/deploy)은 명시적 확인이 필요합니다.

## 인증

webstack은 인증을 번들링하지 않습니다. `/webstack:init` Phase 5에서 사용자에게 묻습니다:

- **Yes** → 백엔드 클래스패스에 `spring-boot-starter-security` 추가, `docs/recipes/spring-security-auth.md`가 SETUP.md에 링크됩니다 (Spring Security 7 + JWT/BCrypt 또는 OAuth2 직접 구현). Supabase Auth는 사용하지 않습니다.
- **No** → Spring Security 미포함. 나중에 인증이 필요하면 피처 PR로 추가합니다.

webstack에서 Supabase는 **관리형 Postgres**로만 사용합니다 (Auth/Storage/Realtime/Edge Functions 미사용). AWS RDS / Neon / 자체 호스팅으로 옮길 때는 `<infra>/supabase.tf` + `DATABASE_URL`만 변경하면 됩니다.

## 기술 스택

| 레이어 | 스택 |
|---|---|
| 프론트엔드 | Next.js 16+ App Router + React 19 + ShadCN + Tailwind v4 + RHF + Zod v4 + TanStack Query v5 + @hey-api/openapi-ts. **FSD-lite** 5계층 (`src/{app, widgets, features, entities, shared}/`). |
| 백엔드 | Spring Boot 4 + Kotlin + DDD/Hexagonal + Spring Modulith 2.x + KoTest BehaviorSpec 6.x + JPA + Flyway + springdoc-openapi + TestContainers. Spring Security는 init 시 옵트인. |
| 인프라 | Vercel (Hobby) + Oracle Cloud Always Free (Ampere A1 ARM) + Supabase (관리형 Postgres) + **OpenTofu** 1.10+ |
| 컨트랙트 | OpenAPI 3.1 |

## 새 스택으로 확장

`shared/` (기술 무관 방법론) vs `docs/` (기술 종속 가이드) 분리 의도:

- 새 스택 추가: `docs/<frontend-or-backend-or-infra>-<stack>/`에 문서 추가, `agents/<stack>-implementer.md` SubAgent 추가, `skills/build-<stack>/SKILL.md` 서브 스킬 추가.
- `shared/`는 스택을 가로질러 안정.

## 문제 해결

영문 README의 Troubleshooting 섹션 참고: [README.md](README.md#troubleshooting).

## 라이선스

MIT — LICENSE 참조.

## 기여

PR 환영합니다. 제출 전 `npm run lint:md && npm run lint:json && npm run lint:yaml` 실행해주세요.
