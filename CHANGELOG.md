# Changelog

All notable changes to webstack will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-26

### Deferred to v0.2

- Destructive-bash hooks (`rm -rf` / `git push --force` confirmation gating). Spec §13 originally listed PreToolUse hooks for "위험한 명령" but v0.1 ships secret-isolation hooks only (block_env_read.py + block_env_bash.py). Destructive-bash protection arrives in v0.2.
- Pact consumer-driven contract testing — drift detection via springdoc only in v0.1.
- Accessibility auditor SubAgent (WCAG checks).
- DB schema designer / migration planner / infra cost estimator SubAgents.
- Real-provider API integration tests (would burn quota; manual sandbox only).
- Pre-commit secret scanning (gitleaks/trufflehog) auto-setup — flagged as SUGGESTION only.
- Remote Terraform backend (Supabase Postgres / S3-compatible).

### Added

- Initial plugin skeleton: `.claude-plugin/plugin.json`, `marketplace.json`
- 4 user-facing slash commands: `/webstack:init`, `/webstack:feature`, `/webstack:infra`, `/webstack:deploy`
- 6 skills (init, feature, infra, deploy, build-be, build-fe — last two as sub-skills)
- 10 SubAgents (feature-architect, backend-implementer, frontend-implementer, test-runner, code-reviewer, contract-drift-detective, terraform-plan-analyzer, security-auditor, design-system-architect, brand-archetype-matcher)
- 30 reference documents (8 methodologies + 3 conventions + 5 templates + 5 frontend + 4 backend + 5 infrastructure)
- PreToolUse hooks for `.env*` Read protection + SessionStart hook
- 4 E2E test scenarios (init, feature, infra, security)
- GitHub Actions CI (markdownlint, jsonlint, yamllint, plugin metadata validation)

### Tech Stack

- 1차 hardcoded: NextJS + ShadCN + Tailwind v4 / Spring Boot 3 + Kotlin + KoTest BehaviorSpec + DDD/Hexagonal / Vercel + Oracle Cloud + Supabase + Terraform
- 모듈화 확장: `docs/<stack>/` 단위로 plug-in 가능

### Architecture

- shared/(SSOT, 기술 무관) + docs/(기술 종속) 분리
- 메인이 Skill orchestrate, 큰 컨텍스트·일관성·격리 작업은 SubAgent로
- Multi-repo + git worktree 기반 진짜 병렬 feature 개발
- OpenAPI 3.1 contract-first + @hey-api/openapi-ts FE codegen + AI BE 직접 작성 + springdoc drift 검증
- 시크릿: 환경변수 + Claude Code deny rule + terraform `sensitive` 마킹
