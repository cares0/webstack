# ADR & C4 model (decision records + auto-generated diagrams)

> Reference for build-be SubAgent and feature-architect SubAgent and code-reviewer SubAgent.
> Architecture Decision Records using webstack's ADR template + auto-generated C4 diagrams via Spring Modulith Documenter.

---

## What is ADR + C4 in webstack

Every non-trivial technical decision in a webstack project leaves two artifacts: an **Architecture Decision Record (ADR)** that captures _why_, and a **C4 diagram** that captures _what_ the resulting system looks like.

ADRs are short, immutable markdown files committed alongside the code. Each lives in `docs/adr/NNNN-<slug>.md` in the relevant repository (BE first; FE and Infra optional) and is never deleted — only superseded or deprecated. They answer "why does the codebase look like this?" for engineers joining months later and for the AI SubAgents that operate on it today.

C4 diagrams are generated, not drawn. Spring Modulith's `Documenter` class introspects the running module structure at test time and emits PlantUML files to `build/spring-modulith-docs/`. CI archives these as build artifacts; the diagrams are always current because they are derived from the source of truth — the code.

Together, ADRs and C4 diagrams form the **living architecture documentation** layer of a webstack project: decisions explain intent; diagrams confirm structure.

---

## Why ADR

Software teams make hundreds of architectural decisions per year. Without a record, each decision is at risk of being silently reversed (a newcomer re-implements what was rejected), cargo-culted (the pattern outlives the constraints that produced it), or unresolvable in review (two engineers re-argue a settled question with no written record).

ADRs prevent all three failure modes. A short file — four sections, rarely more than one page — creates a searchable, version-controlled, code-adjacent record of reasoning. When constraints change, the ADR is superseded with a reference to its successor.

For AI SubAgents specifically, ADRs are the mechanism by which historical context crosses session boundaries. The `feature-architect` SubAgent reads existing ADRs before proposing a new module shape; the `code-reviewer` SubAgent checks that an implementation is consistent with accepted decisions. Without ADRs, every agent session starts from zero context.

Benefits: decisions traceable in git history (who/when/why); onboarding faster (unusual patterns explained); architecture review faster (alternatives already on record); AI agents can reason about prior commitments before suggesting changes.

---

## ADR template

webstack ships a canonical template at [`shared/templates/adr-template.md`](../../shared/templates/adr-template.md). Do not duplicate it here — cross-link and use it. Fields: **Status** (lifecycle state), **Context** (forces at play, factual — no advocacy), **Decision** ("We will `<verb>` `<object>`." — one sentence; if it cannot fit in one sentence the decision is too broad), **Consequences** (easier/harder/new constraints — honest about downsides), **Alternatives considered** (rejected options with one-line reasons), **References** (spec, RFC, prior art, related ADRs).

The template follows Michael Nygard's 2011 format — the most widely adopted ADR structure.

### File location and naming

ADRs for the backend: `<project>-backend/docs/adr/NNNN-<slug>.md` (four-digit zero-padded number, lowercase slug with hyphens). Frontend: `<project>-frontend/docs/adr/`. Infrastructure: `<project>-infrastructure/docs/adr/`. When a decision spans all three repositories (e.g., "use JWT for all API authentication"), it lives in the backend ADR directory and is cross-linked from the other repositories' `CLAUDE.md`.

---

## ADR lifecycle

Four states — the `Status` field is the single source of truth:

```
Proposed → Accepted → Deprecated
                  ↓
             Superseded by ADR-NNNN
```

| State | Meaning |
|---|---|
| **Proposed** | Under discussion; PR is open |
| **Accepted** | Decision is final and in effect; PR merged |
| **Deprecated** | No longer applicable; no successor |
| **Superseded by ADR-MMMM** | Replaced by a newer decision; old file stays |

Rules:

1. `Proposed` ADRs travel with the implementing PR — never merged to `main` alone.
2. Decision text is immutable once `Accepted`. Change of mind → new ADR that supersedes the old one.
3. ADRs are never deleted. Cross-links stay valid; git history is the archive.
4. The `Superseded` state must name the successor: `Superseded by ADR-0007`.

---

## webstack convention

**One ADR per significant decision, attached to the PR that enacts it.**

"Significant" means a choice between two defensible alternatives where the rejected ones are not chosen for specific, documentable reasons. The following always need an ADR:

- Selecting a library over an alternative (e.g., jOOQ vs. Spring Data for complex queries).
- Adopting or departing from a webstack default (e.g., disabling the Modulith verifier for a specific module).
- Defining a cross-cutting pattern (outbox event publishing, structured logging format, API versioning strategy).
- Changing an existing accepted decision — write a new ADR that supersedes the old one; do not edit.
- Any infrastructure topology choice (e.g., OCI Object Storage vs. S3-compatible).

**PR attachment rule:** The PR description must link to the ADR it introduces or references. The `code-reviewer` SubAgent checks for this link during P5 review. If a PR introduces structural change and no ADR is linked:

> **IMPORTANT**: This PR changes `<module>` structure / selects `<library>` / departs from a webstack default but has no accompanying ADR. Add `docs/adr/NNNN-<slug>.md` and link it in the PR description before merge.

The `feature-architect` SubAgent creates a draft ADR (`Proposed`) as part of `plan.md` output for every feature that involves a significant technology or pattern decision.

---

## C4 model recap

The C4 model (Simon Brown) organizes architecture diagrams into four levels of abstraction. Each level zooms in from the previous:

### Level 1 — System Context

The widest view. Shows your system as a single box surrounded by users and external systems. Audience: anyone (business stakeholders, new team members). No technology details.

```plantuml
@startuml SystemContext
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Context.puml

Person(user, "Student", "Uses the platform")
System(app, "Pulley Platform", "Spring Boot + Next.js")
System_Ext(payment, "Stripe", "Payment processing")

Rel(user, app, "Uses", "HTTPS")
Rel(app, payment, "Charges", "HTTPS/REST")
@enduml
```

### Level 2 — Container

Zooms into the system boundary. Shows deployable units (Spring Boot jar, Next.js app, Postgres database). Audience: developers and architects. Technology choices appear here. Key containers for webstack: `Next.js App`, `Spring Boot API`, `PostgreSQL`, and external systems like `Stripe`. Use `C4_Container.puml` macros: `Container(...)`, `ContainerDb(...)`, `System_Ext(...)`.

### Level 3 — Component

Zooms into a single container. For the Spring Boot backend, each Modulith module is a component. Shows module interactions via domain events. Audience: backend developers. This is the level Spring Modulith Documenter auto-generates.

```plantuml
@startuml Component
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Component.puml

Container_Boundary(be, "Spring Boot API") {
    Component(billing, "Billing Module", "Spring Modulith", "Invoice lifecycle, payments")
    Component(catalog, "Catalog Module", "Spring Modulith", "Products, pricing")
    Component(order, "Order Module", "Spring Modulith", "Order placement, fulfillment")
    Component(identity, "Identity Module", "Spring Modulith", "Auth, users, roles")
}

Rel(order, billing, "InvoiceRequested event", "ApplicationModuleListener")
Rel(billing, order, "InvoicePaid event", "ApplicationModuleListener")
Rel(order, catalog, "ProductReserved event", "ApplicationModuleListener")
@enduml
```

### Level 4 — Code

Class-level diagram inside a single component. webstack does not require Level 4 diagrams; IDEs generate them on demand. Use only when onboarding developers to a particularly complex aggregate.

The four levels map to the audiences most likely to read them:

| Level | Audience | Maintained by |
|---|---|---|
| 1 — System Context | Everyone | Hand-written, updated rarely |
| 2 — Container | Developers, architects | Hand-written, updated per infrastructure change |
| 3 — Component | Backend developers | **Auto-generated by Modulith Documenter** |
| 4 — Code | Implementers (optional) | IDE or on-demand |

---

## Modulith Documenter auto-generation

Spring Modulith's `Documenter` class reads the live `ApplicationModules` instance at test time and emits PlantUML files. The output is always consistent with the actual package structure — no manual diagram maintenance.

### Dependency

Add `spring-modulith-docs` to the test classpath. With the webstack BOM (always included) no explicit version is needed:

```kotlin
// build.gradle.kts
implementation(platform("org.springframework.modulith:spring-modulith-bom:2.0.6"))
testImplementation("org.springframework.modulith:spring-modulith-docs")
```

### Test class

Place in `src/test/kotlin/com/example/app/`:

```kotlin
package com.example.app

import org.junit.jupiter.api.Test
import org.springframework.modulith.core.ApplicationModules
import org.springframework.modulith.docs.Documenter

class DocumentationTest {

    private val modules = ApplicationModules.of(Application::class.java)

    @Test
    fun `write module documentation`() {
        Documenter(modules)
            .writeDocumentation()
            .writeIndividualModulesAsPlantUml()
            .writeAggregatingDocument()
    }
}
```

The full API chain:

| Method | What it produces |
|---|---|
| `writeDocumentation()` | Calls all generation methods; convenient one-liner for CI |
| `writeModulesAsPlantUml()` | One PlantUML file showing all modules and their relationships (C4 Component level) |
| `writeIndividualModulesAsPlantUml()` | One PlantUML file per module showing that module's direct dependencies |
| `writeModuleCanvases()` | Tabular "canvas" per module: events published, commands handled, exposed beans |
| `writeAggregatingDocument()` | `all-docs.adoc` that includes all generated diagrams and canvases |

### Output directory

Gradle projects: `build/spring-modulith-docs/`

```
build/spring-modulith-docs/
├── all-docs.adoc              # aggregating Asciidoc
├── components.puml            # all-modules C4 component diagram
├── billing.puml               # billing module + direct deps
├── billing-canvas.adoc        # billing module canvas
├── catalog.puml
├── catalog-canvas.adoc
├── order.puml
└── order-canvas.adoc
```

Each `.puml` file is a valid PlantUML source. In CI, PlantUML renders them to SVG and the SVGs are posted to the PR as a comment (see CI integration and PR attach pattern below).

### Diagram style options

The default output style is C4 Component. Switch to UML component notation when the audience prefers it:

```kotlin
val diagramOptions = DiagramOptions.defaults()
    .withStyle(DiagramOptions.DiagramStyle.UML)

Documenter(modules, diagramOptions)
    .writeModulesAsPlantUml()
```

Cross-reference: [`docs/backend/spring-modulith.md`](../backend/spring-modulith.md) covers the broader Modulith documentation generation setup and the `writeDocumentation()` one-liner; this document focuses on the CI-oriented variant.

---

## CI integration

The documentation test runs on every pull request that touches the backend. This guarantees that the C4 diagrams in the PR artifact reflect the exact module structure of the proposed change.

### Gradle task

In `.github/workflows/pr.yml`:

```yaml
- name: Generate architecture diagrams
  run: ./gradlew test --tests "*DocumentationTest"

- name: Upload diagram artifacts
  uses: actions/upload-artifact@v4
  with:
    name: spring-modulith-docs
    path: build/spring-modulith-docs/
    retention-days: 30
```

### Failure handling

If `DocumentationTest` fails, the PR is blocked. Common causes: a module imports from another module's `application/` or `infrastructure/`; `Application.kt` is not at the root package; a new top-level package has no `package-info.java` or `@PackageInfo` annotation. Run locally before pushing:

```bash
./gradlew test --tests "*DocumentationTest" && open build/spring-modulith-docs/
```

---

## PR attach pattern

After `DocumentationTest` passes and the artifact is uploaded, a GitHub Actions step renders the PlantUML diagrams to SVG and posts them as a PR comment. This gives reviewers an immediate visual diff of the module structure.

### GitHub Actions step (optional)

Render the generated `.puml` files to SVG and post them as a PR comment so reviewers see the module graph without downloading artifacts:

```yaml
- name: Render PlantUML diagrams
  uses: cloudbees/plantuml-github-action@master
  with:
    args: -tsvg build/spring-modulith-docs/*.puml

- name: Comment diagrams on PR
  uses: actions/github-script@v7
  if: |
    github.event_name == 'pull_request' &&
    github.event.pull_request.head.repo.full_name == github.repository
  with:
    script: |
      const fs = require('fs');
      const docsDir = 'build/spring-modulith-docs';
      const bodies = fs.readdirSync(docsDir)
        .filter(f => f.endsWith('.svg'))
        .map(f => `### ${f}\n![${f}](${docsDir}/${f})`);
      if (bodies.length === 0) return;
      await github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: `## Architecture diagrams\n\n${bodies.join('\n\n')}`,
      });
```

Requires `issues: write` on `GITHUB_TOKEN`. The `head.repo` guard skips fork PRs where the token lacks write access.

---

## Anti-patterns

**Making a significant decision without an ADR.** "We'll document it later" becomes "we don't know why this was done" within six months. Write the ADR in `plan.md` before the code.

**Writing diagrams by hand.** Hand-drawn Level 3 (Component) diagrams go stale within two weeks of a refactor. The Modulith Documenter eliminates this — generate, do not draw.

**Title-only ADRs.** An ADR with empty `Context` and `Consequences` is a commit message. The `Context` must explain forces at play; the `Consequences` must be honest about trade-offs, including downsides. A decision with no downsides did not require analysis.

**Recording the decision without recording the alternatives.** The `Alternatives considered` section prevents future engineers from re-debating settled questions. "We didn't use X because Y" is the most valuable sentence in an ADR.

**Editing an accepted ADR to change the decision.** The decision text is immutable once `Accepted`. Write a new ADR that supersedes the old one; update the old ADR's `Status` to `Superseded by ADR-NNNN`; leave its body untouched.

**Accumulating ADRs without linking them from code.** Cross-link from the module's `package-info.java` comment or the feature's `CLAUDE.md` to the relevant decisions. The `code-reviewer` SubAgent checks for missing links during P5 review.

---

## Sources

- **Architecture Decision Records (ADR) community repository:** https://github.com/joelparkerhenderson/architecture-decision-record — _community: Joel Parker Henderson_
- **C4 model — Simon Brown:** https://c4model.com/ — _community: Simon Brown_
- **MADR — Markdown Architectural Decision Records:** https://adr.github.io/madr/ — _community: adr.github.io_
- **Spring Modulith Documenter reference:** https://docs.spring.io/spring-modulith/reference/documentation.html — _authoritative: Spring_
- **Michael Nygard — "Documenting Architecture Decisions" (2011):** https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions — _community: Cognitect_
- **C4-PlantUML stdlib:** https://github.com/plantuml-stdlib/C4-PlantUML — _community: plantuml-stdlib_

Last verified: 2026-05-04 (Spring Modulith 2.X / C4 model / ADR / PlantUML).
