# Brand Identity Discovery

> Sources:
>
> - Alina Wheeler, *Designing Brand Identity*, 5th ed. (Wiley, 2017)
> - Carl Jung, archetypes (collected in *The Archetypes and the Collective Unconscious*)
> - Margaret Mark & Carol Pearson, *The Hero and the Outlaw* (2001) — modern 12 archetype framework

## Why brand identity for webstack init

`/webstack:init` derives the design system from the service's identity (not its features). Without a clear identity, design tokens (color, type, motion) are arbitrary — and arbitrary design produces inconsistent UX.

## Wheeler's 5 phases (adapted to AI interview)

1. **Conducting research** — understand market, competitors, audience. (init P1 + P2)
2. **Clarifying strategy** — vision, mission, values, positioning. (init P1)
3. **Designing identity** — visual translation of strategy. (init P3 — design system)
4. **Creating touchpoints** — apply identity across surfaces. (build-fe, ongoing)
5. **Managing assets** — version, distribute, govern. (.webstack/design-system/)

webstack init focuses on phases 1-3 (information capture). Phases 4-5 are ongoing across feature work.

## Interview script (init P1)

The brand-archetype-matcher SubAgent processes user answers through these prompts (English; main agent translates if user input is non-English):

1. **One-line definition** — "What is this service in one sentence? Form: ' for who does what so that '."
2. **Core values (pick 3)** — from a curated list of 30 (e.g., trustworthy, playful, expert, accessible, daring, careful, premium, scrappy, ...). Custom values allowed.
3. **Tone keywords** — 3-7 adjectives describing the voice (e.g., calm/urgent, formal/casual, witty/earnest).
4. **Category** — B2B / B2C / B2B2C / DTC / marketplace / SaaS / consumer mobile / etc. (multi-select where overlapping)
5. **Primary archetype match** (Jung 12) — pick from descriptions:
   - Innocent (Coca-Cola, Dove)
   - Sage (Google, BBC)
   - Explorer (Patagonia, Jeep)
   - Outlaw (Harley-Davidson, Virgin)
   - Magician (Disney, Apple)
   - Hero (Nike, FedEx)
   - Lover (Victoria's Secret, Häagen-Dazs)
   - Jester (Old Spice, M&M's)
   - Everyman (Target, IKEA)
   - Caregiver (Johnson & Johnson, UNICEF)
   - Ruler (Mercedes-Benz, Microsoft)
   - Creator (Lego, Adobe)
6. **Reference (optional)** — Figma URL / mood board image / inspiration list. The agent does NOT auto-fetch external URLs without explicit user permission.

## Output schema (`.webstack/identity.md`)

See the `identity.md` schema in `shared/schemas.md`.

## Mapping archetype → design tokens (used by design-system-architect)

| Archetype | Color tendency | Type tendency | Motion |
|---|---|---|---|
| Innocent | soft pastels, white, cream | rounded sans, generous letter-spacing | gentle, organic |
| Sage | desaturated blues/grays | classic serif or geometric sans | precise, measured |
| Explorer | earth tones, terracotta, forest | rugged sans, slab-serif accents | bold, energetic |
| Outlaw | high contrast, black/red | aggressive display | abrupt, kinetic |
| Magician | deep purples, navy + gold | elegant serif | smooth, transformative |
| Hero | bold primary (red, blue), white | strong sans, condensed | decisive, fast |
| Lover | warm pinks, plum, gold | refined serif or script | flowing, intimate |
| Jester | bright yellows, oranges, pink | playful display, varied weights | bouncy, surprising |
| Everyman | neutrals, tan, navy | humanist sans | comfortable, predictable |
| Caregiver | soft blues, greens, beige | rounded humanist | gentle, reassuring |
| Ruler | navy, gold, charcoal | classical serif, structured | refined, deliberate |
| Creator | varied, often saturated | mix display + neutral | inventive, layered |

These are tendencies, not rules. The design-system-architect SubAgent uses this mapping as input plus user reference plus persona context.

## References

- Wheeler, *Designing Brand Identity* (2017).
- Mark & Pearson, *The Hero and the Outlaw* (2001).
- Jung, *The Archetypes and the Collective Unconscious* (1959).
- IDEO field guides on brand sprints.
