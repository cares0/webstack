# Design System Extraction

> Sources:
> - Adam Wathan & Steve Schoger, *Refactoring UI* (2018)
> - Material Design 3 tokens (https://m3.material.io/foundations/design-tokens/overview)
> - Brad Frost, *Atomic Design* (2016)
> - Tailwind CSS theme philosophy (Adam Wathan)

## Token categories (Refactoring UI + Material 3 hybrid)

### Color

- **Brand**: primary, secondary (optional). Each has 9-11 step scale (50-950).
- **Semantic**: success, warning, danger, info. Use restraint — 1 of each.
- **Neutral**: background, foreground, muted, border. 9-11 step scale of grays (or cool/warm tinted gray).
- **Surface**: elevation tints (subtle).

Refactoring UI rule: don't pick 5 colors at once. Pick 1-2 brand colors + a gray scale + 3 semantic accents. That's it.

### Typography

- **Font family**: 1 sans-serif primary, 1 mono (for code). Optional: 1 display for headings.
- **Type scale**: 6-8 sizes following modular ratio (e.g., 1.25 minor third, 1.333 perfect fourth). xs, sm, base(16px), lg, xl, 2xl, 3xl, 4xl.
- **Weight**: 400 (normal), 500 (medium), 600 (semibold), 700 (bold). Don't use all 9 weights — 3-4 max.
- **Line-height**: tighter for display (1.1-1.25), looser for body (1.5-1.7).
- **Letter-spacing**: slightly negative for large display (-0.02em), normal for body, slightly positive for small caps/labels (+0.05em).

### Spacing

- **Scale**: 0, 1, 2, 3, 4, 6, 8, 12, 16, 20, 24, 32, 48, 64 (in `0.25rem` units = 4px). Tailwind default.
- **Why this scale**: doubled-rhythm-ish, not strictly geometric — matches visual intuition.

### Radius

- 4 sizes: `sm` (2-4px), `md` (6-8px, default), `lg` (12-16px), `full` (9999px for pills/avatars).

### Shadow

- 4 levels: `sm` (1-2px subtle border alt), `md` (cards), `lg` (popovers), `xl` (modals).
- Refactoring UI rule: shadows have a slight downward y-offset and natural color tint (not pure black).

### Motion

- **Duration**: fast (100-150ms — micro-interactions), normal (200-300ms — page transitions), slow (400-500ms — modals).
- **Easing**: standard (`cubic-bezier(0.4, 0.0, 0.2, 1)`), entry (`cubic-bezier(0.0, 0.0, 0.2, 1)`), exit (`cubic-bezier(0.4, 0.0, 1, 1)`).
- **Reduced motion**: respect `prefers-reduced-motion`. Replace transitions with instant or fade-only.

## Extraction algorithm (design-system-architect SubAgent)

Input: identity.md + persona.md + (optional) reference URLs/images.
Output: tokens.json + theme.css + component-variants.md.

```
1. Determine archetype palette tendency (from brand-identity-discovery.md table).
2. Adjust by persona constraints:
   - Low vision → bump contrast to AA+ (4.5:1 body, 3:1 large).
   - Senior → larger type base (17-18px), more spacing.
   - Mobile primary → 16px base minimum (iOS no-zoom rule).
3. Pick base hue from archetype + tone keywords. Generate 11-step scale (50-950) using OKLCH.
4. Pick neutral scale tint (cool/warm) from archetype. Generate 11 steps.
5. Pick semantic accents (success green, warning amber, danger red, info blue) — desaturate to harmonize with brand.
6. Pick type families:
   - Sans: from short curated list (Inter, Geist Sans, Pretendard for KR, IBM Plex Sans, Manrope, ...).
   - Mono: JetBrains Mono / Geist Mono / IBM Plex Mono.
7. Set type scale ratio based on density preference (1.25 default).
8. Set spacing scale (Tailwind default unless specific need).
9. Set radius preset (small=brutalist, medium=default, large=friendly).
10. Set shadow preset (none/subtle/elevated).
11. Set motion preset (subtle/standard/playful) — reduced-motion respected.
12. Map all tokens to ShadCN CSS variables (theme.css).
13. Define core component variants:
    - Button: primary, secondary, ghost, destructive, outline.
    - Card: default, elevated, outlined.
    - Input: default, error, disabled.
    - Badge: primary, secondary, success, warning, danger.
14. Output to tokens.json + theme.css + component-variants.md.
15. Ask user to confirm or iterate.
```

## ShadCN CSS variable mapping

ShadCN uses HSL CSS variables in `:root` and `.dark`. Map our tokens:

```css
:root {
  --background: <neutral-50 in hsl>;
  --foreground: <neutral-950 in hsl>;
  --card: <neutral-50 in hsl>;
  --card-foreground: <neutral-950 in hsl>;
  --popover: <neutral-50 in hsl>;
  --popover-foreground: <neutral-950 in hsl>;
  --primary: <brand-600 in hsl>;
  --primary-foreground: <neutral-50 in hsl>;
  --secondary: <neutral-100 in hsl>;
  --secondary-foreground: <neutral-900 in hsl>;
  --muted: <neutral-100 in hsl>;
  --muted-foreground: <neutral-500 in hsl>;
  --accent: <neutral-100 in hsl>;
  --accent-foreground: <neutral-900 in hsl>;
  --destructive: <danger-600 in hsl>;
  --destructive-foreground: <neutral-50 in hsl>;
  --border: <neutral-200 in hsl>;
  --input: <neutral-200 in hsl>;
  --ring: <brand-600 in hsl>;
  --radius: <radius-md>;
}
.dark { /* mirrored for dark mode */ }
```

## Refactoring UI rules to remember

1. Use color **and** spacing to convey hierarchy — not just bold.
2. Hover/focus must be obvious to keyboard-only users.
3. White space is a feature, not waste.
4. Real photos > stock illustrations (most of the time).
5. Don't design in the middle — start with extreme states (empty/loading/error/full) first.

## References

- Wathan & Schoger, *Refactoring UI* (2018).
- https://m3.material.io/foundations/design-tokens/overview
- Frost, *Atomic Design* (2016).
- https://oklch.com/ for color picking.
