---
name: deploy
description: Use when deploying frontend (Vercel auto-deploy via git push) or backend (Oracle Cloud manual deploy via SCP + systemd) after feature completion. Pre-flight runs security-auditor; tests must pass; user confirms target. Streams deployment status until success/failure.
disable-model-invocation: true
---

# deploy skill — application deployment

You are running `/webstack:deploy`. Push code to production. Confirm everything; deployments are user-visible and partially irreversible.

## Reference docs (lazy — read on demand)

These references are loaded **lazily** — do NOT preload at P0. When a phase below names a doc, Read it at that point only.

- `docs/infrastructure/vercel-setup.md`
- `docs/infrastructure/oracle-cloud-setup.md`
- `shared/conventions/git-workflow.md`
- `docs/infrastructure/release-management.md`
- `docs/infrastructure/observability-stack.md`
- `docs/infrastructure/backup-and-recovery.md`

## Pre-flight (P0)

1. Verify `<project_root>/.webstack/manifest.yaml` and infra was applied (manifest has `vercel_project_url` + `oracle_instance_public_ip` + `supabase_project_url` keys mirrored from `tofu output`).
2. Invoke `security-auditor` SubAgent on all 3 repos. Block on Critical.
3. For frontend: `cd <fe-repo> && git status --porcelain` empty + on main + main is up to date with origin (`git fetch && git rev-list HEAD..origin/main` is empty). If not: surface to user.
4. For backend: same checks.
5. For both: verify tests pass on main: invoke `test-runner` SubAgent against both repos' main checkout (not worktrees).
6. Show pre-flight summary; confirm: "Pre-flight clean. Proceed to choose deploy target?"

## Phase 1: Target selection

Ask user:

> "Which to deploy?
>
> 1. Frontend (Vercel auto-deploys main)
> 2. Backend (SCP jar + systemd restart on Oracle VM)
> 3. Both"

Capture choice. Confirm: "About to deploy `<choice>`. Type `deploy` to proceed."

## Phase 2: Frontend deploy (if selected)

Vercel auto-deploys on push to main. Since pre-flight already checks main = origin/main, simply:

1. Confirm Vercel project linked: read `manifest.yaml` for vercel_project_id.
2. Print URL: `https://vercel.com/<team>/<project>` for user to monitor.
3. Optionally: poll Vercel REST API (`GET /v9/projects/<id>/deployments`) every 10s, surface state changes (BUILDING → READY / ERROR), max 10 minutes.
4. On ERROR: fetch latest deployment build logs URL; show to user.
5. On READY: print final URL.

## Phase 3: Backend deploy (if selected)

1. Build jar:

   ```bash
   cd <be-repo> && ./gradlew clean bootJar -x test --no-daemon
   ```

   (test was already run in pre-flight; skip rerun.)
2. Locate jar: `ls build/libs/*.jar` and pick the executable jar (Spring Boot's `bootJar` task emits a single fat jar). If multiple, pick the one without `-plain.jar` suffix.
3. SCP jar + env file to Oracle VM (host = `oracle_instance_public_ip` from manifest; user = `ubuntu` per the Ubuntu 22.04 ARM image documented in `docs/infrastructure/oracle-cloud-setup.md`):

   ```bash
   scp -i ~/.ssh/<key> build/libs/app.jar ubuntu@<oracle_instance_public_ip>:/opt/app/app.jar
   scp -i ~/.ssh/<key> deploy/app.env ubuntu@<oracle_instance_public_ip>:/opt/app/app.env
   ```

   Notes:
   - The systemd unit `webstack-app.service` (provisioned by `cloud-init.yaml` during `/webstack:infra`) reads `/opt/app/app.env` for `DATABASE_URL`, `SUPABASE_*`, etc.
   - `deploy/app.env` is a per-deploy environment file you assemble locally from the manifest + sensitive `tofu output -raw` values; never commit it (gitignore `deploy/app.env`).
   - The user must have configured the SSH key during `/webstack:infra` (the public key was injected via `oci_core_instance.metadata.ssh_authorized_keys`).
4. Restart the service (service name is fixed: `webstack-app.service`):

   ```bash
   ssh -i ~/.ssh/<key> ubuntu@<oracle_instance_public_ip> "sudo systemctl restart webstack-app.service && sudo systemctl status webstack-app.service --no-pager"
   ```

5. Wait 15-30s for boot. Health-check:

   ```bash
   curl -fsS https://<api-domain>/actuator/health | jq .status
   ```

   Expected: `"UP"`. If not, retry 3 times with 10s spacing; if still failing, tail journalctl and surface to the user:

   ```bash
   ssh -i ~/.ssh/<key> ubuntu@<oracle_instance_public_ip> "sudo journalctl -u webstack-app.service --no-pager -n 100"
   ```

## Phase 4: Result + summary

Update `manifest.yaml`:

- `last_deploy.frontend.timestamp` (if FE deployed)
- `last_deploy.frontend.commit_sha`
- `last_deploy.backend.timestamp`
- `last_deploy.backend.commit_sha`

Print:

> Deploy complete.
>
> - Frontend: `https://<vercel-domain>/` (commit `<sha>`)
> - Backend: `https://<api-domain>/` (commit `<sha>`)
>
> Monitor: <vercel dashboard url>, <oracle metrics URL>.

## Escalation Protocol

If pre-flight fails: do NOT proceed. Surface findings, ask user to resolve (e.g., merge feature PRs, fix flaky test, rotate token if security-auditor flagged a leak).

If deploy fails partway: show error, ask user — rollback (`git revert` + redeploy) or hot-fix forward.

## Style

- Show every command before running.
- Echo command output to user verbatim (truncate to last 30-50 lines for long output).
- For polling phases: progress indicator (1 line per state change).
