# Persona Creation

> Sources:
>
> - Alan Cooper, *About Face: The Essentials of Interaction Design*, 4th ed. (Wiley, 2014)
> - Dave Gray (XPLANE), Empathy Map Canvas
> - Nielsen Norman Group persona articles

## Why personas for webstack init

A persona translates the abstract "user" into a concrete, decision-shaping character. Design choices flow from "would she do this?" rather than "what's the average?". webstack init derives 1 primary persona (and optionally 1 secondary) to ground the design system in a real usage context.

## Cooper's 7 steps (adapted)

1. **Identify behavioral variables** — interview real users or domain expert; map activities, attitudes, aptitudes, motivations, skills.
2. **Map subjects to variables** — cluster.
3. **Identify significant patterns** — clusters that appear across multiple variables = persona seed.
4. **Synthesize characteristics & goals** — flesh out the seed.
5. **Check redundancy & completeness** — primary persona's needs should drive most design decisions.
6. **Designate persona types** — primary, secondary, supplemental.
7. **Develop narrative & details** — name, photo (avoid stock cliché), quote, day-in-the-life.

In webstack init P2, the agent runs an abbreviated version: capture goals, pain points, context, device, frequency. Skip behavioral variable mapping for 1차 (added in v2 if needed).

## Cooper's persona content checklist

- **Demographics**: age, occupation, location, household.
- **Goals** (3 levels):
  - End goals: what they want from the product (e.g., "track my expenses without spreadsheets").
  - Experience goals: how they want to feel using it (e.g., "in control", "not judged").
  - Life goals: longer-term motivation that shapes choices (e.g., "save for my child's education").
- **Pain points** with current alternatives.
- **Usage context**: where, when, on what device, with what attention level (focused/distracted), under what time pressure.
- **Quote** that captures their attitude.

## Empathy mapping (XPLANE) supplement

For each persona, capture:

- **Says**: literal quotes.
- **Thinks**: internal beliefs, sometimes contradicting "Says".
- **Does**: observed behavior.
- **Feels**: emotional state.
- **Pains**: frustrations, blockers, anxieties.
- **Gains**: aspirations, what they value.

The webstack persona schema (`personas/primary.md` in `shared/schemas.md`) includes the Cooper essentials. Empathy map fields can be added inline if user provides them.

## Anti-patterns

- **Marketing personas**: demographic-heavy, behavior-light. Useless for design decisions.
- **Stock personas**: generic "Sarah, 32, marketing manager" — no specific goals.
- **Persona inflation**: 7 personas means none drive decisions. Stick to 1-2 primary.

## How design-system-architect uses persona

- **Color/contrast**: low-vision context → AA+ contrast minimum. Brand archetype Caregiver + 65+ persona → softer palette, larger type defaults.
- **Type scale**: persona reading on phone in transit → scale skewed larger (16px base).
- **Motion**: persona with vestibular sensitivity → reduced motion preset; brand Jester + Gen Z persona → playful motion within reasonable taste.
- **Density**: persona context "quick glance during workday" → high information density; "evening leisure" → spacious.

## References

- Cooper et al., *About Face* (2014), chapters on personas.
- XPLANE Empathy Map Canvas.
- Nielsen Norman Group, "Personas: Study Guide".
