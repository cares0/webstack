# webstack artifact schemas

> Canonical shapes for the metadata artifacts under `<project_root>/.webstack/`. Skills and SubAgents
> read and write these — keep them in sync. (This file is the shipped home for the artifact schemas that
> a development-only design spec used to hold; that spec is not part of the published plugin.)

All paths are relative to `<project_root>/.webstack/` unless noted.

---

## identity.md  (written by `/webstack:init` Phase 1)

Markdown with a YAML front-matter block plus prose. Captures the brand identity used to derive the design system.

```markdown
---
one_line_definition: "<service in one sentence>"
core_values: [<value1>, <value2>, <value3>]        # exactly 3
tone_keywords: [<kw>, ...]                          # 3-7
category: [<B2B|B2C|B2B2C|SaaS|marketplace|...>]    # 1+ (multi-select allowed)
archetype:
  primary: <one of the 12>                          # Innocent|Sage|Explorer|Outlaw|Magician|Hero|Lover|Jester|Everyman|Caregiver|Ruler|Creator
  supplemental: <one of the 12 or null>
  confidence: High|Medium|Low
reference_assets: [<path-or-url>, ...]              # optional; never auto-fetched
---

# Identity: <project>

## What we stand for
<2-4 sentences synthesizing values + archetype voice>

## Tone
<how the product speaks — bullet the tone keywords with one example each>
```

The 12 archetype names are fixed (Mark & Pearson). See `methodologies/brand-identity-discovery.md` for the
archetype→token tendency table consumed by `design-system-architect`.

---

## personas/primary.md  (and optional secondary.md — written by `/webstack:init` Phase 2)

Cooper-format persona. One file per persona.

```markdown
---
name: <made-up name>
age: <int>
occupation: <string>
location: <string>
type: primary | secondary
---

# Persona: <name>

## Goals
- **End goal**: <what they want from the product>
- **Experience goal**: <how they want to feel using it>
- **Life goal**: <longer-term motivation that shapes choices>

## Pain points
- <frustration with current alternatives>

## Usage context
- Device: <phone | desktop | tablet | mixed>
- Environment: <where/when>
- Frequency: <daily | weekly | ...>
- Attention level: <focused | distracted>

## Quote
> "<one line capturing their attitude>"
```

Empathy-map fields (Says/Thinks/Does/Feels/Pains/Gains) may be appended inline if the user provides them.
See `methodologies/persona-creation.md`.

---

## design-system/tokens.json  (written by `design-system-architect` in `/webstack:init` Phase 3)

Structured JSON. All colors in **OKLCH** (modern ShadCN convention). `theme.css` and `component-variants.md`
are derived from this. See `methodologies/design-system-extraction.md`.

```json
{
  "color": {
    "brand": { "50": "oklch(...)", "100": "oklch(...)", "...": "...", "950": "oklch(...)" },
    "neutral": { "50": "oklch(...)", "...": "...", "950": "oklch(...)" },
    "semantic": {
      "success": "oklch(...)", "warning": "oklch(...)",
      "danger":  "oklch(...)", "info":    "oklch(...)"
    }
  },
  "typography": {
    "fontFamily": { "sans": "<family>", "mono": "<family>", "display": "<family|null>" },
    "scaleRatio": 1.25,
    "weights": [400, 500, 600, 700],
    "lineHeight": { "display": 1.15, "body": 1.6 },
    "letterSpacing": { "display": "-0.02em", "body": "0", "label": "0.05em" }
  },
  "spacing": "tailwind-default",
  "radius": { "preset": "sm|md|lg", "base": "<rem>" },
  "shadow": { "preset": "none|subtle|elevated" },
  "motion": {
    "duration": { "fast": "120ms", "normal": "240ms", "slow": "440ms" },
    "easing": { "standard": "cubic-bezier(0.4,0,0.2,1)", "entry": "cubic-bezier(0,0,0.2,1)", "exit": "cubic-bezier(0.4,0,1,1)" },
    "respectsReducedMotion": true
  }
}
```

`color.brand` and `color.neutral` are 11-step scales (50–950). Contrast pairs must pass WCAG AA (verified by the agent).

---

## manifest.yaml  (written by `/webstack:init` completion; updated by feature/infra/deploy)

Single source of project metadata. Skills read flags from here ("Project flags (read first)").

```yaml
project:
  name: <kebab-case>
  created_at: <ISO-8601>
  needs_auth: false              # set in init Phase 5

optional_integrations:           # set in init Phase 5.5; absent => all false except renovate
  observability: false
  i18n: false
  renovate: true
  release_management: false

repos:
  frontend: <abs-or-relative path>
  backend: <path>
  infrastructure: <path>

last_phase:
  init: completed                # completed | in_progress
  # infra / deploy stamped by their skills

infrastructure:                  # mirrored from `tofu output` by /webstack:infra (non-sensitive only)
  vercel_project_id: <id>
  vercel_project_url: <url>
  oracle_instance_public_ip: <ip>
  supabase_project_url: <url>
  # sensitive outputs (database_url, db password) are NOT stored here — retrieve via `tofu output -raw <name>`

features:                        # appended by /webstack:feature Phase 8
  - name: <feature>
    status: in_review            # planned | in_review | merged
    frontend_pr: <url>
    backend_pr: <url>

last_deploy:                     # stamped by /webstack:deploy Phase 4
  frontend: { timestamp: <ISO>, commit_sha: <sha> }
  backend:  { timestamp: <ISO>, commit_sha: <sha> }
```

---

## ../<infrastructure-repo>/.env.template  (written by `/webstack:init` Phase 6)

Placeholders only — **never** real values. The user copies to `.env`, fills it, and exports with
`set -a && source .env && set +a`. OpenTofu reads the `TF_VAR_*` prefix automatically. AI never reads `.env`
(deny rules + PreToolUse hooks). Keep this list in sync with `infrastructure/variables.tf` (every var marked
`sensitive = true`).

```bash
# Vercel
TF_VAR_vercel_token=

# Oracle Cloud (OCI)
TF_VAR_oci_tenancy_ocid=
TF_VAR_oci_user_ocid=
TF_VAR_oci_fingerprint=
TF_VAR_oci_private_key_path=
TF_VAR_oci_region=

# Supabase (managed Postgres only)
TF_VAR_supabase_access_token=
TF_VAR_supabase_db_password=
```

Projects that opt into auth or optional integrations add the corresponding vars here as those features land.
