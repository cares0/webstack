# webstack — 풀스택 웹 개발 하네스 설계 명세

| 항목 | 값 |
|---|---|
| 작성일 | 2026-04-26 |
| 작성 도구 | superpowers:brainstorming → writing-plans |
| 결과물 의존 | superpowers와 무관(stand-alone Claude Code plugin) |
| 1차 사용자 | 본인 + Claude Marketplace/GitHub 일반 공개 |
| 1차 hardcoded 스택 | NextJS + ShadCN + Tailwind v4 / Spring Boot 3 + Kotlin + KoTest BehaviorSpec + DDD/Hexagonal / Vercel + Oracle Cloud + Supabase + Terraform |
| 확장성 의도 | 스킬·SubAgent·docs 모듈화로 다른 스택 plug-in 가능(예: docs/django/, docs/vue/) |

---

## 1. 개요 (Overview)

### 1.1 목적

`webstack`은 Claude Code에서 **풀스택 웹 서비스의 신규 빌드 사이클**을 — 프로젝트 정체성 인터뷰부터 디자인 시스템 도출, 멀티-repo 스캐폴딩, feature 기획·API 합의·BE/FE 구현·인프라 IaC·배포까지 — 하나의 일관된 워크플로우로 가이드하는 plugin이다.

### 1.2 핵심 가치

1. **검증된 외부 방법론 위에 구축** — Lean Startup의 hypothesis-driven, Cooper persona, Refactoring UI 토큰 도출, Eric Evans/Vaughn Vernon DDD, Alistair Cockburn Hexagonal Architecture, OpenAPI 3.1 contract-first, Anthropic 권장 SubAgent 패턴, Cursor/Devin 멀티 agent role 패턴(Planner/Architect/Implementer/Tester/Reviewer)을 자체 형태로 재구성.
2. **Single Source of Truth(SSOT) + 기술-종속 분리** — 기술 무관 일반 방법론은 `shared/`에, 1차 hardcoded 기술 종속 가이드는 `docs/`에. 다른 스택 plug-in 시 `docs/`만 추가하면 됨.
3. **사용자(개발자) 안전장치** — 시크릿이 AI에 직접 노출되지 않는 구조, destructive 작업(terraform apply, git push, deploy)은 명시 컨펌, multi-repo + git worktree 기반 진짜 병렬 feature 작업.
4. **단계별 명시적 흐름** — 4개 진입 슬래시 명령(init·feature·infra·deploy). init 1회, feature N회 병렬, infra·deploy는 사용자 명시 호출.

### 1.3 비-목적 (Non-goals)

- **MVP 범위/기능 한정 같은 비즈니스 기획**은 다루지 않는다 (init은 기능 무관, brand identity + persona + design system + 셋업만).
- **다른 기술 스택의 1차 지원**은 없다 (1차는 명시 스택만, 향후 plug-in으로 확장).
- **Pact 같은 consumer-driven contract testing**은 1차에서 다루지 않는다 (1인 사용엔 무거움; v2 옵션).

---

## 2. 결정 로그 (Decision Log)

22가지 핵심 결정. 각 결정은 본문에서 상세 설명.

| # | 결정 | 대안 | 선정 이유 |
|---|---|---|---|
| 1 | 1차 hardcoded 스택 + 모듈화 확장 구조 | 처음부터 일반 공개 / 본인 전용만 | requirements의 "플러그인으로 진화"와 일치 |
| 2 | 한 문서에 모든 스킬 상세 (단일 spec) | 분해 sub-spec | 사용자 선택 — 일관성 우위 |
| 3 | superpowers와 무관, 자체 구현 | dependency / 영감만 | 사용자 명시 |
| 4 | 도메인 + 보조 워크플로우, 공용은 SSOT 문서 | 도메인만 / 통합 | 사용자 통찰 |
| 5 | init = 디자인 시스템 + FE/BE/IaC 셋업 (기능 무관) | MVP 범위 포함 / 통합 | 사용자 명시 |
| 6 | 디자인 시스템 = 토큰 + ShadCN 테마 + 핵심 컴포넌트 variants | 토큰만 / 풀 brand book | 깊이·인터뷰 시간 균형 |
| 7 | init 인터뷰 phase = 정체성→페르소나→디자인 시스템 + reference 옵션 | 2/4 phase | 검증된 방법론 3종 결합 |
| 8 | 호출 모델 = init(1회) + feature(N회 병렬) + infra + deploy | 단일 마스터 / 평면 7개 | 사용자 통찰(병렬 + 직관성) |
| 9 | git worktree 기반 병렬 feature | 브랜치만 | 사용자 요구 — 병렬 충돌 방지 |
| 10 | 이름: webstack | harness/atelier/loom 등 | 직관성 |
| 11 | infra = 별도 스킬 (init 분리) | init 통합 / deploy 통합 | 사용자 수동 가입 단계 분리 |
| 12 | Multi-repo (3개 git repo) | Monorepo / Hybrid | 사용자 결정 |
| 13 | 시크릿 = 환경변수 + Claude Code deny rule + terraform sensitive | 1Password / Keychain / 다층 | 사용자 결정 — 미니멀 |
| 14 | 메타는 부모 디렉토리 `.webstack/` | 4번째 git repo / 사용자 홈 | 1인 단순성 |
| 15 | API contract = OpenAPI 3.1 + @hey-api/openapi-ts FE codegen + AI BE 직접 작성 + springdoc drift 검증 | TypeScript shared / GraphQL / backend-first | 검증된 contract-first 패턴 |
| 16 | Skills 6개 + SubAgents 10개 (build-be/fe sub-skill + SubAgent 둘 다 유지) | sub-skill만 / SubAgent만 | DRY + 메인 fallback + 격리/병렬화 |
| 17 | `.webstack/` 디렉토리 구조 = manifest+identity+personas+design-system+contracts+features+SETUP | 단일 manifest yaml / all markdown | 도메인별 분리 + 형식 정합 |
| 18 | phase 인벤토리 (각 스킬 P0~P6/P8) | — | spec 핵심 |
| 19 | shared/(SSOT, 기술 무관) + docs/(기술 종속) 분리 | 통합 references/ | 사용자 통찰 — 모듈화 |
| 20 | 인터뷰 언어: 영어 (사용자 입력 follow) | 한국어 / 이중어 | 마켓플레이스 적합 |
| 21 | Reference Tier 1 (~25개) | 전체 ~50 / 최소 ~10 | 출시 속도 + 일관성 균형 |
| 22 | SubAgent + Skill 둘 다, SubAgent가 Skill invoke | 통합 / sub-skill 폐지 | DRY + production-grade |

---

## 3. 시스템 아키텍처

### 3.1 진입점 (4 슬래시 명령)

| 명령 | 호출 빈도 | 진입 조건 | 산출물 |
|---|---|---|---|
| `/webstack:init` | 프로젝트당 1회 | 빈 디렉토리, `.webstack/` 부재 | 디자인 시스템 + FE/BE/Infra 3개 git repo + `.webstack/` 메타 + SETUP.md |
| `/webstack:feature <name>` | feature당 1회, 병렬 N개 | `.webstack/` 존재 | feature worktree(FE+BE) + plan + contract + 구현 코드 + 테스트 + PR 생성 안내 |
| `/webstack:infra` | 1회 + 인프라 변경 시 N회 | infrastructure repo + `.env` 존재(값 미접근) | terraform plan 분석 + 사용자 컨펌 + apply + 환경변수 연결 |
| `/webstack:deploy` | 배포 시 N회 | main branch + tests pass | Vercel push (FE) + Oracle Cloud deploy (BE) + 모니터링 |

### 3.2 책임 분담 — 메인 vs Skill vs SubAgent

- **메인 (도메인 슬래시 명령의 호출자)**: 사용자와 직접 인터뷰, 단계별 컨펌·체크포인트, SubAgent 결과 통합, escalate 메시지 처리.
- **Skill (`skills/<name>/SKILL.md`)**: 재사용 가능한 행동 가이드. 도메인 슬래시 명령의 phase 흐름 (init/feature/infra/deploy) 또는 sub-skill (build-be/build-fe). progressive disclosure로 시작 시 description만 시스템 프롬프트에, body는 invoke 시 로드.
- **SubAgent (`agents/<name>.md`)**: 별도 컨텍스트의 specialist. 자체 system prompt + 제한된 도구 set. 메인이 Task tool로 invoke. SubAgent가 Skill tool 가지고 있으면 자체 컨텍스트에서 Skill invoke 가능 (예: backend-implementer가 build-be skill invoke).
- **Reference 문서 (`shared/*` + `docs/*`)**: 정적 원칙·체크리스트·기술 가이드. Skill·SubAgent의 system prompt에서 imperative ("Required: Read shared/methodologies/tdd.md before proceeding")로 강제 read.

### 3.3 데이터 흐름

```
init
 ├─ identity.md (정체성)
 ├─ personas/primary.md (페르소나)
 ├─ design-system/{tokens.json, theme.css, component-variants.md}
 ├─ frontend repo, backend repo, infrastructure repo (3 git repos)
 └─ SETUP.md (가입 가이드)
       │
       ▼ (사용자가 가입+토큰 입력)
infra
 ├─ terraform plan → 변경 분류 → 사용자 컨펌 → apply
 └─ manifest.yaml 갱신 (인프라 메타)
       │
       ▼ (반복)
feature <name>
 ├─ worktrees: frontend/.worktrees/<name>, backend/.worktrees/<name>
 ├─ plan-feature → features/<name>/plan.md
 ├─ sync-contract → contracts/<name>.yaml (OpenAPI 3.1)
 ├─ backend-implementer (병렬) — DDD 코드 + KoTest
 ├─ frontend-implementer (병렬) — codegen + 컴포넌트 + 테스트
 ├─ test-runner → BE/FE 테스트 실행
 ├─ code-reviewer + contract-drift-detective (병렬)
 └─ PR 생성 안내
       │
       ▼ (배포 시)
deploy
 ├─ Vercel push (FE) / Oracle deploy (BE)
 └─ 모니터링 + 결과 보고
```

---

## 4. 디렉토리 구조

### 4.1 Plugin 디렉토리 (`webstack/`)

```
webstack/                              # plugin root, marketplace 배포 단위
├── .claude-plugin/
│   ├── plugin.json                    # name, version, description, dependencies
│   └── marketplace.json               # marketplace 메타
├── commands/                          # 슬래시 명령 → skill invoke
│   ├── init.md
│   ├── feature.md
│   ├── infra.md
│   └── deploy.md
├── skills/
│   ├── init/SKILL.md                  # 슬래시 명령용 phase 흐름
│   ├── feature/SKILL.md               # 슬래시 명령용 (Planner role 포함)
│   ├── infra/SKILL.md
│   ├── deploy/SKILL.md
│   ├── build-be/SKILL.md              # 구현 가이드 — backend-implementer가 invoke (또는 메인 fallback)
│   └── build-fe/SKILL.md              # 구현 가이드 — frontend-implementer가 invoke (또는 메인 fallback)
├── agents/                            # SubAgents (10개)
│   ├── feature-architect.md           # Architect — 메타 분석 → 도메인 매핑
│   ├── backend-implementer.md         # Implementer (BE) — DDD layered 코드
│   ├── frontend-implementer.md        # Implementer (FE) — App Router 코드
│   ├── test-runner.md                 # Tester — KoTest/Vitest/Playwright 실행
│   ├── code-reviewer.md               # Reviewer — 컨벤션·타입 안전성
│   ├── contract-drift-detective.md    # Reviewer (specialized) — springdoc vs OpenAPI diff
│   ├── terraform-plan-analyzer.md     # Analyst — plan output 분류
│   ├── security-auditor.md            # Auditor — 시크릿/deny rule 검사
│   ├── design-system-architect.md     # Specialist (init) — 토큰 + variants 도출
│   └── brand-archetype-matcher.md     # Specialist (init) — Jung archetype 매칭
├── shared/                            # SSOT — 기술 무관 일반 방법론 (stable)
│   ├── methodologies/                 # ~8 문서
│   ├── conventions/                   # ~3 문서
│   └── templates/                     # ~5 문서
├── docs/                              # 1차 hardcoded 기술 종속 가이드 (plug-in 단위)
│   ├── frontend/                      # NextJS/ShadCN/Tailwind 등 ~5 문서
│   ├── backend/                       # Spring/Kotlin/KoTest/JPA 등 ~4 문서
│   └── infrastructure/                # Vercel/Oracle/Supabase/Terraform ~5 문서
├── hooks/
│   └── hooks.json                     # (필요 시) PreToolUse 등
├── tests/                             # 자체 검증 (E2E 시나리오)
├── README.md
├── CLAUDE.md                          # plugin 사용 가이드
└── package.json
```

추후 plug-in 확장 시:
- 새 BE 스택: `docs/backend-django/` 추가 + `agents/backend-implementer-django.md` 추가 + `skills/build-be-django/SKILL.md` 추가. 기존 `shared/`는 변경 없음.
- 새 FE 스택: 동일.
- 새 인프라: `docs/infrastructure-aws/` 추가 등.

### 4.2 사용자 프로젝트 디렉토리 (Multi-repo + 메타)

```
~/projects/<project>/                  # 부모 디렉토리 (사용자 선택)
├── .webstack/                         # 메타 (부모 디렉토리에 위치, git 별도 선택)
│   ├── manifest.yaml                  # 전역 메타 (스택, 플러그인 버전, 인프라 메타 인덱스)
│   ├── identity.md                    # 정체성 인터뷰 결과
│   ├── personas/
│   │   └── primary.md                 # 1차 페르소나
│   ├── design-system/
│   │   ├── tokens.json                # 디자인 토큰 (color/typography/spacing/radius/shadow/motion)
│   │   ├── theme.css                  # ShadCN 테마 — frontend repo로 복사
│   │   └── component-variants.md      # 핵심 컴포넌트 variants 정의
│   ├── contracts/                     # OpenAPI 3.1 명세 (feature가 채움)
│   │   └── <feature>.yaml
│   ├── features/                      # feature별 상태 (병렬 N개)
│   │   └── <feature>/
│   │       ├── plan.md
│   │       ├── worktree-paths.yaml    # FE/BE worktree 경로 추적
│   │       ├── be-status.md
│   │       └── fe-status.md
│   └── SETUP.md                       # init 마지막 phase 산출 — 가입+토큰 가이드
├── <project>-frontend/                # git repo (NextJS + pnpm)
│   ├── .worktrees/<feature>/          # feature 작업 시 생성
│   └── ...
├── <project>-backend/                 # git repo (Spring + Gradle)
│   ├── .worktrees/<feature>/
│   └── ...
└── <project>-infrastructure/          # git repo (Terraform)
    ├── .env.template                  # commit 가능 (placeholder만)
    ├── .gitignore                     # .env, .env.local 차단
    ├── .claude/settings.local.json    # Read/Bash deny rule
    └── ...
```

### 4.3 Worktree 정책

- 위치: 각 repo 내부 `.worktrees/<feature-name>/` (`.gitignore`에 추가됨, sibling 옵션도 제공)
- feature 호출 시 frontend, backend 양쪽 worktree 생성. branch명: `feature/<feature-name>`.
- worktree 경로는 `.webstack/features/<feature-name>/worktree-paths.yaml`에 기록.
- 완료 시 PR 생성 후 worktree 삭제 안내 (사용자 명시 컨펌).

---

## 5. Skills 명세

각 SKILL.md는 다음 구조를 따른다:

```yaml
---
name: <skill-name>
description: <invocation hint - progressive disclosure>
---

# <skill-name>

## Required reads
- shared/methodologies/X.md
- docs/<frontend|backend|infrastructure>/Y.md

## Phase flow
... (P0-P_n)

## Checkpoints
... (사용자 컨펌 위치)

## Outputs
... (산출물 명세)

## Escalation
... (SubAgent로 위임 시점)
```

### 5.1 `init` (도메인, 슬래시)

**Description (frontmatter)**: "Use when starting a new fullstack web service from scratch — runs identity/persona interviews, derives design system, scaffolds frontend/backend/infrastructure repos. Run once per project."

**Required reads**:
- `shared/methodologies/brand-identity-discovery.md`
- `shared/methodologies/persona-creation.md`
- `shared/methodologies/design-system-extraction.md`
- `docs/frontend/nextjs-app-router.md`
- `docs/frontend/shadcn-customization.md`
- `docs/backend/spring-modulith.md`
- `docs/infrastructure/setup-guide.md`

**Phase 흐름**:

| Phase | 책임 | SubAgent invoke | 산출물 | 체크포인트 |
|---|---|---|---|---|
| P0 Pre-flight | 메인 | — | 검증 결과 (디렉토리 비어있음, gh CLI 설치, terraform optional) | abort 시 알림 |
| P1 정체성 인터뷰 | 메인 (인터뷰) | `brand-archetype-matcher` (Jung 12 archetype 매칭) | `.webstack/identity.md` | "다음 phase로 진행?" |
| P2 페르소나 인터뷰 | 메인 (인터뷰) | — | `.webstack/personas/primary.md` | "다음 phase로 진행?" |
| P3 디자인 시스템 도출 | 메인 (인터뷰) | `design-system-architect` (토큰 후보 + variants 도출) | `tokens.json` + `theme.css` + `component-variants.md` | "이 토큰 + variants로 진행?" |
| P4 Frontend repo 스캐폴딩 | 메인 (`gh repo create` + `create-next-app` + ShadCN init + theme 적용) | — | `<project>-frontend/` git repo | "다음 phase로 진행?" |
| P5 Backend repo 스캐폴딩 | 메인 (Spring Initializr + Hexagonal layers + KoTest deps) | — | `<project>-backend/` git repo | "다음 phase로 진행?" |
| P6 Infrastructure repo 스캐폴딩 + 가입 가이드 | 메인 (terraform module skeleton + .env.template + .gitignore + .claude/settings.local.json deny rule + SETUP.md) | — | `<project>-infrastructure/` git repo + SETUP.md | "init 완료. SETUP.md 따라 가입 후 /webstack:infra 실행하세요." |
| 완료 | 메인 (manifest.yaml 작성) | — | `.webstack/manifest.yaml` | — |

### 5.2 `feature` (도메인, 슬래시)

**Description**: "Use when adding a new feature to an existing webstack project. Creates worktrees, runs plan/contract interviews, and orchestrates parallel BE/FE implementation via subagents."

**Required reads**:
- `shared/methodologies/feature-planning.md`
- `shared/methodologies/api-first.md`

**Phase 흐름**:

| Phase | 책임 | SubAgent invoke | 산출물 | 체크포인트 |
|---|---|---|---|---|
| P0 Pre-flight | 메인 | — | 검증 (`.webstack/` 존재, working tree 클린, feature 이름 유효) | abort 시 알림 |
| P1 Worktree 생성 | 메인 (Bash: `git worktree add`) | — | `frontend/.worktrees/<name>`, `backend/.worktrees/<name>` + `worktree-paths.yaml` | — |
| P2 plan-feature 인터뷰 | 메인 (Planner role — 사용자 인터뷰) | — | `features/<name>/plan.md` | "이 plan으로 진행?" |
| P2.5 도메인 매핑 분석 | — | `feature-architect` (메타 분석 → aggregate/화면/스킬 제안) | architect report (메인이 plan에 반영) | — |
| P3 sync-contract | 메인 (architect 결과 반영하여 OpenAPI 3.1 작성) | — | `contracts/<name>.yaml` | "이 명세로 진행?" |
| P4-P5 병렬 구현 | 메인 (Task multiple parallel calls) | `backend-implementer` + `frontend-implementer` (병렬) | BE/FE worktree commits + status.md | escalate 메시지 시 사용자 인터뷰 → 재 invoke |
| P6 테스트 실행 | — | `test-runner` (KoTest/Vitest/Playwright) | test report | failing test 시 사용자에게 알림 |
| P7 리뷰 | — | `code-reviewer` + `contract-drift-detective` (병렬) | review report + drift report | critical issue 시 사용자에게 보고 |
| P8 통합 결과 + PR 생성 안내 | 메인 (`gh pr create` 옵션) | — | PR URL (생성 시) | "PR 생성?" / worktree 삭제 안내 |

### 5.3 `infra` (도메인, 슬래시)

**Description**: "Use when applying or modifying infrastructure (Vercel/Oracle/Supabase via Terraform). Always reports plan changes and asks for confirmation before apply."

**Required reads**:
- `docs/infrastructure/terraform-modules.md`
- `docs/infrastructure/vercel-setup.md`
- `docs/infrastructure/oracle-cloud-setup.md`
- `docs/infrastructure/supabase-setup.md`
- `shared/methodologies/secret-management.md`

**Phase 흐름**:

| Phase | 책임 | SubAgent invoke | 산출물 | 체크포인트 |
|---|---|---|---|---|
| P0 Pre-flight | 메인 | `security-auditor` (deny rule 적용 여부, .env commit 검사) | 검증 결과 (terraform CLI, .env 존재 — 값 미접근) | abort |
| P1 terraform init/plan | 메인 (Bash: `terraform plan -no-color -out=plan.tfplan`) | — | `plan.tfplan` (binary, gitignore) | — |
| P2 변경 분석 | — | `terraform-plan-analyzer` (plan output 파싱 → create/modify/destroy 분류 + 위험도) | 변경 요약 리포트 | "이 변경으로 진행? (Y/N)" — destructive(modify/destroy) 시 강조 |
| P3 terraform apply | 메인 (Bash: `terraform apply plan.tfplan` — sensitive 마킹 + apply 자체는 사용자 컨펌 후 실행) | — | apply 결과 + state | apply 실패 시 rollback 안내 |
| P4 결과 요약 + 환경변수 연결 | 메인 (manifest.yaml 갱신, FE/BE repo의 .env.local 업데이트 안내) | — | manifest 갱신 + 연결 가이드 | — |

### 5.4 `deploy` (도메인, 슬래시)

**Description**: "Use when deploying frontend (Vercel) or backend (Oracle Cloud) after feature completion."

**Required reads**:
- `docs/infrastructure/vercel-setup.md`
- `docs/infrastructure/oracle-cloud-setup.md`

**Phase 흐름**:

| Phase | 책임 | SubAgent invoke | 산출물 | 체크포인트 |
|---|---|---|---|---|
| P0 Pre-flight | 메인 | `security-auditor` (시크릿 누출 + deny rule + .env commit 검사) | 검증 결과 (main branch, tests pass) | abort |
| P1 배포 대상 선택 | 메인 (인터뷰) | — | 선택 결과 (FE/BE/둘 다) | "이 대상으로 배포?" |
| P2 배포 실행 | 메인 (Vercel은 `git push origin main` → Vercel 자동, BE는 Oracle deploy 명령) | — | 배포 시작 | — |
| P3 모니터링 + 결과 보고 | 메인 (Vercel API/Oracle API 폴링 + 로그 fetch) | — | 배포 상태 리포트 | 실패 시 rollback 안내 |

### 5.5 `build-be` (sub-skill — backend-implementer가 invoke 또는 메인 fallback)

**Description**: "Use when implementing backend code from an OpenAPI contract. Follows DDD/Hexagonal architecture with Spring Boot 3 + Kotlin + KoTest BehaviorSpec."

**Required reads**:
- `shared/methodologies/ddd.md`
- `shared/methodologies/hexagonal.md`
- `shared/methodologies/api-first.md`
- `shared/methodologies/tdd.md`
- `docs/backend/spring-modulith.md`
- `docs/backend/kotest-behavior-spec.md`
- `docs/backend/jpa-patterns.md`
- `docs/backend/jooq-patterns.md`

**Phase 흐름** (worktree 안에서 작업):

| Phase | 산출물 |
|---|---|
| P1 contract 분석 → DDD aggregate 도출 | `domain/<aggregate>/` 폴더 + entity + value object |
| P2 application service + use case 작성 | `application/<usecase>/` |
| P3 infrastructure adapter (controller, repository) 작성 | `infrastructure/<adapter>/` |
| P4 KoTest BehaviorSpec 작성 (TDD: spec 먼저, 구현 채움) | `test/<aggregate>/` |
| P5 springdoc 기반 drift 검증 (`contract-drift-detective` SubAgent invoke) | drift report |

### 5.6 `build-fe` (sub-skill — frontend-implementer가 invoke 또는 메인 fallback)

**Description**: "Use when implementing frontend code from an OpenAPI contract. Uses NextJS App Router + ShadCN + Tailwind v4 + RHF/Zod + TanStack Query."

**Required reads**:
- `shared/methodologies/tdd.md`
- `shared/methodologies/clean-code.md`
- `docs/frontend/nextjs-app-router.md`
- `docs/frontend/server-components.md`
- `docs/frontend/server-actions.md`
- `docs/frontend/shadcn-customization.md`
- `docs/frontend/tailwind-v4.md`
- `docs/frontend/rhf-zod.md`
- `docs/frontend/tanstack-query.md`

**Phase 흐름** (worktree 안에서 작업):

| Phase | 산출물 |
|---|---|
| P1 codegen | `src/api/generated/` (@hey-api/openapi-ts) |
| P2 page route 작성 | `src/app/<route>/page.tsx` (App Router) |
| P3 Server/Client Component 분리 → ShadCN 컴포넌트 작성 | `src/components/<feature>/` |
| P4 form (RHF + Zod) + data fetch (TanStack Query) | form 컴포넌트 + query/mutation 훅 |
| P5 test (Vitest + RTL + Playwright) | unit/integration/e2e 테스트 |

---

## 6. SubAgents 명세

각 agents/<name>.md는 다음 구조 (superpowers 패턴 따름):

```markdown
---
name: <agent-name>
description: <when this agent is delegated to>
model: inherit
---

You are <role>. Your task is <responsibility>.

## Inputs
- ...

## Required reads
- ...

## Outputs
- ...

## Escalation Protocol
If you encounter a decision requiring user input, output:
`CLARIFICATION NEEDED: <specific question>`
and stop. Main will handle user interaction and re-invoke with answer in context.

## Tool restrictions
- Allowed: Read, Grep, Glob (read-only) | or Read/Write/Edit/Bash (full)
- Forbidden: ...
```

### 6.1 SubAgent 인벤토리 (10개)

| # | 이름 | Role | 도구 set | 사용처 | 핵심 책임 |
|---|---|---|---|---|---|
| 1 | `feature-architect` | Architect | Read, Grep, Glob | feature P2.5, build-be P1 | 기존 메타(contracts·features·identity·personas·design system) 분석 → 새 feature의 aggregate/화면/모듈 매핑 제안 |
| 2 | `backend-implementer` | Implementer (BE) | Read, Write, Edit, Bash, Grep, Glob | feature P4 | build-be skill invoke → DDD layered 코드 작성 (worktree 안) |
| 3 | `frontend-implementer` | Implementer (FE) | Read, Write, Edit, Bash, Grep, Glob | feature P5 | build-fe skill invoke → App Router 코드 작성 (worktree 안) |
| 4 | `test-runner` | Tester | Read, Bash | feature P6 | KoTest/Vitest/Playwright 실행 + 결과 분석 |
| 5 | `code-reviewer` | Reviewer | Read, Grep, Glob | feature P7, build-be P5, build-fe P5 | DDD/Hexagonal/Server-Client 컨벤션 + 타입 안전성 + Critical/Important/Suggestion 분류 |
| 6 | `contract-drift-detective` | Reviewer (specialized) | Read, Bash(GET 만 — springdoc actuator endpoint) | build-be P5, feature P7 | springdoc runtime 명세 vs `.webstack/contracts/<feature>.yaml` diff |
| 7 | `terraform-plan-analyzer` | Analyst | Read, Bash(plan only — no apply/destroy) | infra P2 | plan output 파싱 → create/modify/destroy 분류 + 리소스 위험도 평가 |
| 8 | `security-auditor` | Auditor | Read, Grep, Glob | deploy P0, infra P0 | 시크릿 노출(.env commit, 패턴 매칭) + Claude Code deny rule 적용 여부 + `--dangerously-skip-permissions` 검사 |
| 9 | `design-system-architect` | Specialist (init) | Read, Edit (theme.css만) | init P3 | identity + persona → Refactoring UI 토큰 후보 도출 + ShadCN theme 매핑 + 컴포넌트 variants 정의 |
| 10 | `brand-archetype-matcher` | Specialist (init) | Read | init P1 | 사용자 정체성 답 → Jung 12 archetypes 매칭 + 톤 키워드 도출 |

### 6.2 SubAgent system prompt 패턴 (예시)

#### `backend-implementer.md` (요지)

```markdown
---
name: backend-implementer
description: Use when implementing backend code in build-be phase of /webstack:feature. Follows DDD/Hexagonal with Spring Boot 3 + Kotlin + KoTest BehaviorSpec. Operates inside the backend repo's .worktrees/<feature>/ directory.
model: inherit
---

You are a Senior Backend Engineer specializing in Domain-Driven Design and Hexagonal Architecture with Spring Boot 3 and Kotlin.

## Your task
Implement backend code from an OpenAPI 3.1 contract following webstack conventions.

## Inputs (provided in invoke prompt)
- `worktree_path`: absolute path to `<repo>/.worktrees/<feature>/`
- `contract_path`: absolute path to `.webstack/contracts/<feature>.yaml`
- `plan_path`: absolute path to `.webstack/features/<feature>/plan.md`
- `feature_architect_report`: aggregate/module mapping suggestion

## Required reads (before any code change)
1. **Skill**: `skills/build-be/SKILL.md` — invoke via Skill tool. Follow phase flow strictly.
2. `shared/methodologies/ddd.md`
3. `shared/methodologies/hexagonal.md`
4. `docs/backend/spring-modulith.md`
5. `docs/backend/kotest-behavior-spec.md`

## Outputs
- BE code commits in worktree (DDD layered structure: domain/, application/, infrastructure/)
- KoTest BehaviorSpec files
- `be-status.md` summary at `.webstack/features/<feature>/be-status.md`

## Escalation Protocol
If you encounter a decision requiring user input (aggregate naming, field type, index strategy, exception policy, etc.), output:
`CLARIFICATION NEEDED: <specific question with 2-3 options>`
and stop. Main agent will handle user interaction and re-invoke with answer in your prompt.

Do NOT guess on naming, types, or business rules.
```

#### `terraform-plan-analyzer.md` (요지)

```markdown
---
name: terraform-plan-analyzer
description: Use after `terraform plan` is generated. Parses plan output and classifies changes (create/modify/destroy) with risk assessment. Read-only — never executes apply.
model: inherit
---

You are a Terraform plan analyst. Your task is to parse a plan output and produce a structured change report.

## Inputs
- `plan_path`: path to plan.tfplan or plan output file

## Allowed actions
- Read plan.tfplan via `terraform show -json <plan>`
- Read terraform module files for context

## Forbidden
- `terraform apply`, `terraform destroy`, any state modification

## Outputs
- Markdown report:
  - **Summary**: N create / M modify / K destroy
  - **By resource type**: per-resource details
  - **Risk Assessment**: Low / Medium / High per resource (with reasoning)
  - **Free-tier impact**: estimated quota usage if applicable

## Escalation Protocol
None — this is read-only analysis. Report ambiguous resources with risk=Unknown and explain.
```

(나머지 8개는 같은 패턴으로 작성. 자세한 system prompt는 plugin 구현 시 작성.)

---

## 7. Reference 문서 인벤토리 (Tier 1, ~30개)

Tier 1은 1차 출시에 포함 — 8 methodologies + 3 conventions + 5 templates + 5 frontend + 4 backend + 5 infrastructure = **30개**. 결정 #21에서 합의된 ~25에서 약간 확장(RHF/TanStack Query 분리 + setup-guide 추가). Tier 2는 v2에 추가.

### 7.1 `shared/methodologies/` (8개)

| 파일 | 출처 |
|---|---|
| `tdd.md` | Kent Beck, *TDD by Example*; Refactoring 원칙 |
| `ddd.md` | Eric Evans, *Domain-Driven Design* (Blue Book); Vaughn Vernon, *Implementing Domain-Driven Design* (Red Book) |
| `hexagonal.md` | Alistair Cockburn 원전 + Baeldung 정리 |
| `api-first.md` | OpenAPI 3.1 표준 + Glovo Engineering / Schwarz IT contract-first 사례 |
| `clean-code.md` | Robert Martin, *Clean Code* 핵심 |
| `brand-identity-discovery.md` | Alina Wheeler, *Designing Brand Identity*; Carl Jung 12 archetypes |
| `persona-creation.md` | Alan Cooper, *About Face*; empathy mapping (XPLANE) |
| `design-system-extraction.md` | Adam Wathan & Steve Schoger, *Refactoring UI*; Material Design tokens |

### 7.2 `shared/conventions/` (3개)

| 파일 | 내용 |
|---|---|
| `git-workflow.md` | Branch naming (`feature/<name>`, `hotfix/<name>`), worktree 정책 |
| `conventional-commits.md` | Conventional Commits 1.0 |
| `pr-template.md` | PR 작성 가이드 + checklist |

### 7.3 `shared/templates/` (5개)

| 파일 | 용도 |
|---|---|
| `adr-template.md` | Architecture Decision Record |
| `design-doc-template.md` | Design Doc (소형) |
| `prd-template.md` | Product Requirements Document (feature plan용) |
| `openapi-spec-template.yaml` | OpenAPI 3.1 starter |
| `kotest-spec-template.kt` | KoTest BehaviorSpec template (Given/When/Then) |

### 7.4 `docs/frontend/` (5개)

| 파일 | 출처 |
|---|---|
| `nextjs-app-router.md` | Next.js 공식 docs (App Router, route groups, layouts, parallel routes) |
| `server-components.md` | RSC 분리 정책 + use client 가이드 |
| `shadcn-customization.md` | ShadCN 공식 + theme.css + components.json |
| `tailwind-v4.md` | Tailwind v4 변경점 (CSS variable 통합, @apply 정책) |
| `rhf-zod.md` | React Hook Form + Zod 폼 패턴 |
| `tanstack-query.md` | Query/Mutation, query key 관리, optimistic update |

### 7.5 `docs/backend/` (4개)

| 파일 | 출처 |
|---|---|
| `spring-modulith.md` | Spring Modulith 공식 + JetBrains 2026 블로그 |
| `kotest-behavior-spec.md` | KoTest 공식 docs |
| `jpa-patterns.md` | Spring Data JPA + lazy/eager + association |
| `jooq-patterns.md` | jOOQ 공식 (선택적, Supabase 직접 SQL이 자연스러우면 Tier 2로) |

### 7.6 `docs/infrastructure/` (5개)

| 파일 | 내용 |
|---|---|
| `vercel-setup.md` | Vercel 가입, project 생성, env 변수, deploy hook |
| `oracle-cloud-setup.md` | Oracle Cloud Always Free, Compute Instance, Network |
| `supabase-setup.md` | Supabase 가입, project 생성, schema design, RLS |
| `terraform-modules.md` | Terraform module 구성, sensitive 변수, plan 형식 |
| `setup-guide.md` (init이 SETUP.md 생성 시 base) | 가입 단계 + 토큰 발급 + .env 입력 + 환경변수 export 가이드 |

### 7.7 Tier 2 (v2)

- `shared/methodologies/`: bdd, systematic-debugging, code-review-checklist, security-principles
- `docs/frontend/`: server-actions (분리), performance, testing (Vitest/Playwright)
- `docs/backend/`: validation, exception-handling, transactional, repository-pattern
- `docs/infrastructure/`: monitoring, ci-cd

---

## 8. 데이터 모델

### 8.1 `manifest.yaml` schema (예시)

```yaml
webstack:
  version: "0.1.0"
  created_at: "2026-04-26T12:00:00Z"
  
project:
  name: "myapp"
  description: "한 줄 정의 (init P1에서 도출)"
  
stack:
  frontend: "nextjs-shadcn-tailwind-v4"
  backend: "spring-kotlin-ddd-kotest"
  infrastructure: "vercel-oracle-supabase-terraform"
  
repos:
  frontend: "myapp-frontend"
  backend: "myapp-backend"
  infrastructure: "myapp-infrastructure"
  
infrastructure:
  vercel_project_url: "<set after first /webstack:infra apply>"
  oracle_compartment_id: "<set after first apply>"
  supabase_project_url: "<set after first apply>"
  
last_phase:
  init: completed
  infra: completed
  
features:
  - name: "user-login"
    status: completed
    pr_url: "https://github.com/..."
  - name: "user-profile"
    status: in_progress
    current_phase: "build-be"
```

### 8.2 `identity.md` schema (예시)

```markdown
# <project> identity

## One-line definition
<service의 한 줄 정의>

## Core values (3)
1. <value 1>
2. <value 2>
3. <value 3>

## Brand archetype (Jung 12)
Primary: <archetype>
Secondary: <archetype, optional>

## Tone keywords
- <keyword 1>
- <keyword 2>
- <keyword 3>

## Target category
<B2B / B2C / B2B2C / etc.>

## Reference (optional)
- Figma URL: ...
- Mood board: ...
```

### 8.3 `personas/primary.md` schema (Cooper format)

```markdown
# Primary persona: <name>

## Demographics
- Age, occupation, location

## Goals
- ...

## Pain points
- ...

## Usage context
- Device, environment, frequency, time-of-day

## Quote
> "..."
```

### 8.4 `design-system/tokens.json` schema (예시)

```json
{
  "color": {
    "primary": "...",
    "secondary": "...",
    "background": "...",
    "foreground": "...",
    "muted": "...",
    "accent": "...",
    "destructive": "...",
    "border": "..."
  },
  "typography": {
    "font_family_sans": "...",
    "font_family_mono": "...",
    "scale": {"xs": "...", "sm": "...", "base": "...", "lg": "...", "xl": "...", "2xl": "..."}
  },
  "spacing": {"unit": "0.25rem", "scale": [0, 1, 2, 3, 4, 6, 8, 12, 16]},
  "radius": {"sm": "...", "md": "...", "lg": "..."},
  "shadow": {"sm": "...", "md": "...", "lg": "..."},
  "motion": {"duration_fast": "...", "duration_normal": "...", "easing": "..."}
}
```

### 8.5 `contracts/<feature>.yaml` (OpenAPI 3.1 starter)

```yaml
openapi: 3.1.0
info:
  title: <feature> API
  version: 0.1.0
servers:
  - url: http://localhost:8080
paths:
  /api/<resource>:
    get:
      summary: ...
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/<Schema>'
components:
  schemas:
    <Schema>:
      type: object
      properties: ...
```

### 8.6 `features/<feature>/plan.md` schema

```markdown
# Feature plan: <name>

## Goal
<feature의 목적>

## User stories
- As a <persona>, I want to <action>, so that <benefit>

## Screens / Routes
- /<route>: <description>

## Functions / Behaviors
- ...

## Business rules
- ...

## Data model impact
- New aggregates: ...
- Modified aggregates: ...

## Out of scope
- ...
```

---

## 9. API 컨트랙트 동기화 메커니즘

### 9.1 Contract-First 흐름

```
plan.md (feature P2)
  │ AI extract resources/operations
  ▼
contracts/<feature>.yaml (OpenAPI 3.1, feature P3)
  │
  ├─[FE]─▶ @hey-api/openapi-ts codegen
  │       └─ src/api/generated/{types.ts, sdk.ts, queries.ts}
  │       └─ frontend-implementer가 import 후 page/component에 적용
  │
  └─[BE]─▶ AI가 명세 보고 직접 작성 (codegen 안 씀)
          ├─ controller (infrastructure layer)
          ├─ DTO (boundary mapping)
          ├─ application service
          ├─ domain (aggregate, entity, value object)
          └─ KoTest BehaviorSpec (TDD: spec 먼저)
          
  └─[Drift 검증]─▶ build-be P5에서 contract-drift-detective SubAgent
          ├─ springdoc-openapi 통합 → /v3/api-docs runtime 명세 fetch
          ├─ contracts/<feature>.yaml과 diff
          └─ 차이 발견 시 사용자에게 보고 + 수정 방향 제안
```

### 9.2 Drift 검증 알고리즘 (요지)

1. backend repo에 `springdoc-openapi-starter-webmvc-ui` 의존성 추가 (init P5에서 자동).
2. `application.yml`에 `springdoc.api-docs.path=/v3/api-docs` 설정.
3. `contract-drift-detective` SubAgent:
   - Bash로 backend 임시 실행 (`./gradlew bootRun &`) 또는 이미 실행 중이라 가정.
   - `curl http://localhost:8080/v3/api-docs` → runtime spec.
   - `.webstack/contracts/<feature>.yaml` 로드.
   - 두 명세 비교: paths, methods, parameters, request/response schemas, status codes.
   - diff 리포트:
     - **Critical**: missing endpoint, status code mismatch, required field missing
     - **Important**: optional field mismatch, description 차이
     - **Info**: example 차이
4. 사용자에게 보고. Critical 시 사용자가 어느 쪽을 진실로 삼을지 결정 (대부분 contract.yaml).

### 9.3 향후 확장 (v2)

- Pact consumer-driven contract testing 통합 (옵션)
- ConnectRPC / GraphQL 스택 plug-in (다른 docs/, 다른 implementer agent)

---

## 10. 시크릿 보안 모델

### 10.1 핵심 원리

**AI는 토큰 값에 절대 접근하지 않는다**. 토큰은 사용자 OS 환경변수에만 존재. terraform 등 도구는 환경변수를 자동 사용하므로 호출자(AI)가 값을 안 봐도 작동.

### 10.2 init이 자동 생성하는 보안 셋업

`infrastructure repo` 초기화 시:

1. `infrastructure/.env.template` (commit 가능 — placeholder만, `TF_VAR_*` prefix는 Terraform이 변수를 자동 감지하기 위함):

   ```
   TF_VAR_vercel_token=
   TF_VAR_oci_tenancy_ocid=
   TF_VAR_oci_user_ocid=
   TF_VAR_oci_fingerprint=
   TF_VAR_oci_private_key_path=
   TF_VAR_oci_region=
   TF_VAR_oci_compartment_id=
   TF_VAR_oci_ssh_public_key_path=
   TF_VAR_supabase_access_token=
   TF_VAR_supabase_organization_id=
   TF_VAR_supabase_db_password=
   ```

2. `infrastructure/.gitignore`에 차단 패턴:
   ```
   .env
   .env.local
   .env.*.local
   *.tfvars
   *.tfvars.json
   .terraform/
   *.tfstate
   *.tfstate.*
   ```

3. `infrastructure/.claude/settings.local.json` deny rules:
   ```jsonc
   {
     "permissions": {
       "deny": [
         "Read(./.env)",
         "Read(./.env.local)",
         "Read(**/.env)",
         "Read(**/.env.local)",
         "Bash(cat .env*)",
         "Bash(printenv *_TOKEN)",
         "Bash(printenv *_KEY)",
         "Bash(printenv *_PASSWORD)",
         "Bash(env)",
         "Bash(env|grep -i token)",
         "Bash(env|grep -i key)",
         "Bash(env|grep -i secret)",
         "Bash(echo $*_TOKEN)"
       ]
     }
   }
   ```

4. `SETUP.md` (사용자 가이드):
   - 각 서비스 가입 URL + 단계
   - 토큰 발급 방법
   - `.env` 파일 작성 (gitignore돼서 commit 안 됨)
   - 셸에 환경변수 export — 매번 수동 (`set -a && source .env && set +a`)
   - 그 후 `/webstack:infra` 실행

### 10.3 Terraform 작성 규칙

- 모든 토큰/비밀 변수는 `sensitive = true`로 마킹:
  ```hcl
  variable "vercel_token" {
    type        = string
    sensitive   = true
  }
  ```
- `terraform plan/apply`는 `-no-color -input=false` 옵션 (stdout 노출 최소화)
- AI가 plan output 분석 시 sensitive 값은 `(sensitive value)`로 마스킹돼서 안 보임

### 10.4 destructive 작업 컨펌 플로우

`terraform apply`, `terraform destroy`, `gh pr merge`, `git push --force` 등은:

1. AI가 명령 실행 전 사용자에게 변경 요약 보고
2. 사용자 컨펌 (Y/N) 후 실행
3. 결과 보고

`terraform-plan-analyzer` SubAgent가 변경 분류(create/modify/destroy)를 명확히 보고하므로 사용자가 의식적으로 컨펌.

### 10.5 한계 (사용자 인지 필요)

- 사용자가 `--dangerously-skip-permissions` 옵션을 켜면 deny rule 우회됨 → 항상 끄고 사용
- IDE의 다른 AI extension은 Claude Code의 deny rule 미적용
- `security-auditor` SubAgent가 위 두 가지를 deploy/infra P0에서 검사 + 보고

---

## 11. Worktree 정책

### 11.1 위치

기본: `<repo>/.worktrees/<feature-name>/` (각 repo 안)

### 11.2 생성 (feature P1)

```bash
# frontend
cd <project>-frontend
git worktree add .worktrees/<feature-name> -b feature/<feature-name>

# backend
cd <project>-backend
git worktree add .worktrees/<feature-name> -b feature/<feature-name>
```

`.webstack/features/<feature>/worktree-paths.yaml`에 절대 경로 기록.

### 11.3 작업 위치

- `backend-implementer` SubAgent는 `cd <backend-repo>/.worktrees/<feature>` 진입 후 작업.
- `frontend-implementer`도 동일.
- 메인은 `.webstack/`만 수정 (worktree 안은 SubAgent 책임).

### 11.4 PR 생성 (feature P8)

```bash
cd <repo>/.worktrees/<feature>
git push -u origin feature/<feature-name>
gh pr create --title "..." --body "..."
```

### 11.5 정리 (PR merge 후)

사용자 컨펌 후:
```bash
git worktree remove .worktrees/<feature-name>
git branch -D feature/<feature-name>  # local
```

---

## 12. 인터뷰 인터랙션 패턴

### 12.1 언어

- SKILL.md, agents/*.md, shared/*, docs/* 등 plugin 문서: **영어**
- 사용자 인터뷰 응답 언어 follow: 사용자가 한국어로 답하면 한국어로 진행, 영어면 영어로

### 12.2 AskUserQuestion 사용

multiple-choice 또는 confirmation은 `AskUserQuestion` tool 활용 (1-4 options, "Other" 자동 제공). 자유 텍스트가 더 적합한 인터뷰는 일반 텍스트 질문.

### 12.3 체크포인트 정책

각 phase 종료 시 사용자에게 체크포인트:
- "이 결과로 다음 phase 진행하시겠습니까?"
- 결과 미리보기 또는 산출 파일 path 안내

### 12.4 escalate 패턴 (SubAgent → 메인 → 사용자)

```
SubAgent: "CLARIFICATION NEEDED: <question>"
   │
   ▼
메인이 메시지 받고 AskUserQuestion으로 사용자에게 질문
   │
   ▼
사용자 답
   │
   ▼
메인이 SubAgent prompt에 답 추가하고 Task 재 invoke
```

---

## 13. Hooks 정책

### 13.1 1차 출시 hooks

- **PreToolUse hook (`Read`)**: `.env*` / `secrets*` / `*.tfstate` 패턴 차단 (deny rule과 별도 보강).
- **PreToolUse hook (`Bash`)**: 위험한 명령 (`rm -rf`, `git push --force` 등)에 컨펌 강제.
- **SessionStart hook**: webstack project 감지 (`.webstack/manifest.yaml` 존재) → 환영 메시지 + 현재 단계 안내.

### 13.2 hooks.json 예시

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/block_env_read.py" }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/block_env_bash.py" }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          { "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/session_start.sh" }
        ]
      }
    ]
  }
}
```

`path_glob` / `command_pattern` style matchers are NOT supported in Claude Code's hook schema — fine-grained file path / command pattern checks live in the helper scripts (`hooks/block_env_read.py`, `block_env_bash.py`) which read `tool_input` JSON from stdin and exit 2 with stderr to block. See those files for the actual deny patterns.

---

## 14. 자체 검증 / 테스트 / 마켓플레이스 배포

### 14.1 E2E 시나리오 (`tests/`)

1. **시나리오 1: 신규 프로젝트 init**
   - 빈 디렉토리에서 `/webstack:init` 호출
   - 정체성/페르소나/디자인 시스템 인터뷰 (mock 응답)
   - 3개 repo 생성 검증, manifest.yaml 검증, SETUP.md 존재 검증

2. **시나리오 2: 첫 feature**
   - init된 프로젝트에서 `/webstack:feature user-login` 호출
   - plan/contract/build-be/build-fe 단계 통과
   - PR 생성 안내까지

3. **시나리오 3: infra 적용 (mock terraform)**
   - mock .env + mock terraform module
   - plan-analyzer 변경 분류 검증
   - destructive 컨펌 플로우 검증

4. **시나리오 4: 보안 격리 검증**
   - .env에 mock 토큰
   - AI가 Read 시도 → deny 검증
   - `printenv VERCEL_TOKEN` 시도 → deny 검증

### 14.2 마켓플레이스 배포 전 체크리스트

- [ ] plugin.json metadata (name, version, description, dependencies, license, repository) 완전성
- [ ] marketplace.json 완전성
- [ ] README.md (사용법, screenshot/예시 흐름)
- [ ] CLAUDE.md (plugin 사용 가이드)
- [ ] LICENSE (MIT 권장)
- [ ] CHANGELOG.md
- [ ] 모든 Tier 1 reference 문서 작성 완료
- [ ] 모든 Skills + SubAgents 작성 완료
- [ ] tests/ 시나리오 4개 통과
- [ ] semantic versioning 적용
- [ ] CI: GitHub Actions로 lint + tests on PR

### 14.3 배포 흐름

1. GitHub repo 생성 (`webstack` 또는 `claude-webstack`)
2. plugin 디렉토리 commit
3. release tag (v0.1.0)
4. Claude Marketplace 등록 (marketplace.json publish)
5. README의 install 명령 (예: `/plugin install webstack`)

---

## 15. 향후 확장 (v2+)

### 15.1 Reference 문서 Tier 2 추가

위 7.7 참조.

### 15.2 SubAgent Tier 2

- `accessibility-auditor`: WCAG 2.x 검증 (FE specific)
- `db-schema-designer`: 도메인 → 정규화 스키마 + 인덱스 제안 (BE specific)
- `infra-cost-estimator`: terraform plan → 무료 한도 초과 알람
- `deployment-monitor`: Vercel/Oracle 배포 상태 폴링 + 로그 분석
- `migration-planner`: DB 스키마 변경 시 Supabase 마이그레이션 플랜 작성

### 15.3 다른 스택 plug-in

- BE: `docs/backend-django/`, `agents/backend-implementer-django.md`, `skills/build-be-django/`
- FE: `docs/frontend-vue/`, `agents/frontend-implementer-vue.md`, `skills/build-fe-vue/`
- 인프라: `docs/infrastructure-aws/`, `agents/aws-plan-analyzer.md`

추가 시 `shared/`는 변경 없음. `manifest.yaml`의 `stack` 필드로 어느 스택을 쓰는지 기록 → init 시 사용자에게 스택 선택지 제시.

### 15.4 Pact consumer-driven contract testing 옵션

팀 사용으로 확장 시 Pact 통합 (build-be P5에 옵션 단계 추가).

### 15.5 plan mode 통합

복잡한 feature는 `/webstack:feature` 시작 시 EnterPlanMode 진입 옵션.

---

## Appendix A — 검증된 외부 출처

### A.1 방법론 출처

- **Brand identity**: Alina Wheeler, *Designing Brand Identity*; Carl Jung 12 archetypes
- **Persona**: Alan Cooper, *About Face: The Essentials of Interaction Design*
- **Design system**: Adam Wathan & Steve Schoger, *Refactoring UI*
- **TDD**: Kent Beck, *Test-Driven Development by Example*
- **DDD**: Eric Evans, *Domain-Driven Design* (Blue Book); Vaughn Vernon, *Implementing Domain-Driven Design* (Red Book)
- **Hexagonal Architecture**: Alistair Cockburn 원전 (2005)
- **Lean Startup (philosophy)**: Eric Ries, *The Lean Startup*

### A.2 기술 출처

- **OpenAPI 3.1 contract-first**:
  - [Baeldung - API First Development with Spring Boot and OpenAPI 3.0](https://www.baeldung.com/spring-boot-openapi-api-first-development)
  - [Glovo Engineering - Using contract-first to build an HTTP Application with OpenAPI and Gradle](https://medium.com/glovo-engineering/using-contract-first-to-build-an-http-application-with-openapi-and-gradle-53b42c2c2094)
  - [Schwarz IT - Contract first with SpringBoot](https://techblog.schwarz/posts/contract-first-with-springboot/)
- **@hey-api/openapi-ts**: [Hey API official](https://heyapi.dev/) (used by Vercel, PayPal, OpenCode)
- **Spring Modulith**: [JetBrains Kotlin Blog 2026](https://blog.jetbrains.com/kotlin/2026/02/building-modular-monoliths-with-kotlin-and-spring/)
- **Hexagonal + DDD + Spring**: [Baeldung Hexagonal Architecture, DDD, and Spring](https://www.baeldung.com/hexagonal-architecture-ddd-spring)

### A.3 SubAgent 패턴 출처

- [Claude Code Docs — Create custom subagents](https://code.claude.com/docs/en/sub-agents)
- [Anthropic — Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Cloudflare — Orchestrating AI Code Review at scale](https://blog.cloudflare.com/ai-code-review/)
- [Calimero - Multi-agent code review](https://github.com/calimero-network/ai-code-reviewer) — 멀티 reviewer 분리 패턴
- [VoltAgent — awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) — 100+ specialized 카탈로그
- [Rick Hightower - Claude Code Subagents and Main-Agent Coordination](https://medium.com/@richardhightower/claude-code-subagents-and-main-agent-coordination-a-complete-guide-to-ai-agent-delegation-patterns-a4f88ae8f46c)
- 표준 5 roles 출처: Cursor, Devin, Aider 패턴

### A.4 사용자 인터뷰에서 합의된 결정 (재참조)

- 결정 1~22: 본 문서 §2 결정 로그 참조

---

## Appendix B — 용어집

- **Skill (Claude Code)**: `skills/<name>/SKILL.md` — 재사용 가능한 행동 가이드. progressive disclosure로 invoke 시 body 로드.
- **SubAgent (Claude Code)**: `agents/<name>.md` — 별도 컨텍스트의 specialist. 자체 system prompt + 제한 도구.
- **SSOT**: Single Source of Truth — 한 곳에서만 정의된 사실/원칙. 본 plugin에서는 `shared/`에 위치.
- **Aggregate (DDD)**: consistency boundary로 묶인 entity 그룹. root entity가 외부 접근 통제.
- **Bounded Context (DDD)**: 도메인 모델이 일관된 의미를 갖는 경계.
- **Contract-first**: 명세 → 구현 방향. 명세가 single source.
- **Drift**: 명세와 구현 사이 불일치.
- **Worktree**: git의 working tree 다중 활성화 메커니즘.
- **escalate (SubAgent)**: SubAgent가 사용자 결정 필요 시 메인에 위임하는 패턴 ("CLARIFICATION NEEDED:").
