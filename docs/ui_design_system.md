# UI Design System

Design system reference for the AI 运营 SaaS dashboard (Vue 3 + Naive UI).

---

## 1. Color Token System

### Rationale for OKLCH

Colors are defined in OKLCH (Oklch lightness–chroma–hue) rather than HSL or hex literals because:

- Lightness in OKLCH is perceptually uniform. A step from L=0.3 to L=0.4 looks the same visual distance regardless of hue. HSL lightness is not uniform — yellow at L=50% appears much brighter than blue at L=50%.
- Chroma can be held constant across hues, producing a neutral ramp where all grays look equally neutral (no blue or green cast).
- Hue is stable: as you lighten or darken a color, the perceived hue stays the same. HSL hue shifts as saturation changes.

### Neutral Ramp

Ten steps from near-black to near-white. Off-black (not pure black) and off-white (not pure white) reduce harsh contrast in text rendering.

```css
:root {
  --color-neutral-50:  oklch(0.97 0.004 264);   /* near-white surface */
  --color-neutral-100: oklch(0.94 0.006 264);
  --color-neutral-200: oklch(0.88 0.008 264);
  --color-neutral-300: oklch(0.80 0.010 264);
  --color-neutral-400: oklch(0.68 0.012 264);
  --color-neutral-500: oklch(0.56 0.012 264);
  --color-neutral-600: oklch(0.44 0.010 264);
  --color-neutral-700: oklch(0.33 0.008 264);
  --color-neutral-800: oklch(0.22 0.006 264);
  --color-neutral-900: oklch(0.14 0.004 264);   /* near-black text */
}
```

### Accent Ramp (Blue — primary brand)

```css
:root {
  --color-accent-50:  oklch(0.96 0.02  255);
  --color-accent-100: oklch(0.91 0.05  255);
  --color-accent-200: oklch(0.83 0.10  255);
  --color-accent-300: oklch(0.73 0.15  255);
  --color-accent-400: oklch(0.63 0.18  255);
  --color-accent-500: oklch(0.54 0.20  255);   /* primary action */
  --color-accent-600: oklch(0.45 0.19  255);
  --color-accent-700: oklch(0.37 0.17  255);
  --color-accent-800: oklch(0.29 0.13  255);
  --color-accent-900: oklch(0.21 0.09  255);
}
```

### Semantic Color Roles

Semantic tokens reference the ramp tokens. Components reference semantic tokens only — never ramp tokens directly.

```css
:root {
  /* Surfaces */
  --surface-base:      var(--color-neutral-50);
  --surface-raised:    #ffffff;
  --surface-overlay:   #ffffff;
  --surface-inset:     var(--color-neutral-100);

  /* Borders */
  --border-default:    var(--color-neutral-200);
  --border-strong:     var(--color-neutral-300);

  /* Text */
  --text-primary:      var(--color-neutral-900);
  --text-secondary:    var(--color-neutral-600);
  --text-muted:        var(--color-neutral-400);
  --text-on-accent:    #ffffff;

  /* Actions */
  --action-primary:    var(--color-accent-500);
  --action-primary-hover: var(--color-accent-600);
  --action-primary-active: var(--color-accent-700);

  /* Status — paired with icons, never hue-only */
  --status-success:    oklch(0.56 0.18  145);
  --status-warning:    oklch(0.68 0.17   75);
  --status-danger:     oklch(0.54 0.22   25);
  --status-info:       var(--color-accent-500);
}
```

### Dark Mode Token Set

Dark mode is a separate token set, not an inverted filter. Accents use lower chroma and higher lightness to maintain legibility on dark surfaces.

```css
[data-theme="dark"] {
  --surface-base:      var(--color-neutral-900);
  --surface-raised:    var(--color-neutral-800);
  --surface-overlay:   var(--color-neutral-700);
  --surface-inset:     oklch(0.10 0.004 264);

  --border-default:    var(--color-neutral-700);
  --border-strong:     var(--color-neutral-600);

  --text-primary:      var(--color-neutral-50);
  --text-secondary:    var(--color-neutral-300);
  --text-muted:        var(--color-neutral-500);

  --action-primary:    var(--color-accent-400);   /* lighter in dark */
  --action-primary-hover: var(--color-accent-300);
  --action-primary-active: var(--color-accent-200);

  --status-success:    oklch(0.68 0.14  145);
  --status-warning:    oklch(0.76 0.14   75);
  --status-danger:     oklch(0.66 0.18   25);
}
```

### WCAG Compliance

- Body text (`--text-primary` on `--surface-base`): minimum 7:1 — AAA. Verify with a contrast checker when tokens change.
- Secondary text (`--text-secondary` on `--surface-base`): minimum 4.5:1 — AA. Required minimum.
- Large text (18pt+ or 14pt+ bold): minimum 3:1 — AA.
- Interactive state is never indicated by hue alone. Every status indicator (task state chip, alert banner) pairs a hue with a distinct icon and a text label.

---

## 2. Typography Scale

One type scale. Ratio: 1.25 (major third). Base: 16px.

| Token | Size | Line height | Usage |
|---|---|---|---|
| `--text-xs`  | 12px | 1.6 | Captions, badges |
| `--text-sm`  | 14px | 1.6 | Table cells, helper text, labels |
| `--text-base`| 16px | 1.55| Body copy |
| `--text-lg`  | 18px | 1.5 | Card titles |
| `--text-xl`  | 20px | 1.45| Section headings |
| `--text-2xl` | 24px | 1.4 | Page headings |
| `--text-3xl` | 30px | 1.3 | Display numbers (KPI cards) |

Line height loosens as size shrinks — smaller text needs more breathing room to remain legible.

**Body measure:** Constrain prose content to 65ch maximum line width to stay within the 45–75 character ideal reading range.

**Font stack:**
```css
--font-sans: "Inter", "PingFang SC", "Hiragino Sans GB", system-ui, sans-serif;
--font-mono: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
```

PingFang SC and Hiragino Sans GB ensure Chinese characters render cleanly on macOS without a separate font load. On Windows, `system-ui` falls back to Segoe UI for Latin and to a system CJK font for Chinese.

**Tabular numerals:** Apply `font-variant-numeric: tabular-nums` to all table columns and KPI displays so numbers align vertically.

---

## 3. Spacing Rhythm

8px base unit. All spacing values are multiples of 4px.

```css
--space-1:   4px;
--space-2:   8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

The vertical rhythm inside a card uses the same values as the rhythm between cards. A card with 24px internal padding has 24px margin between sibling cards. This produces a visually coherent grid without magic numbers.

**Radii:** Three values only.
```css
--radius-sm:  4px;   /* inputs, badges, small chips */
--radius-md:  8px;   /* cards, panels */
--radius-lg: 16px;   /* modal overlays, drawers */
```
Inner elements inside a rounded container use a smaller radius than the container radius to avoid optical radius mismatch.

---

## 4. Elevation

Prefer border + soft shadow over heavy blurs. Strong shadows are reserved for genuinely floating layers.

```css
--shadow-none:  none;
--shadow-sm:    0 1px 2px oklch(0.14 0.004 264 / 0.06);
--shadow-md:    0 2px 8px oklch(0.14 0.004 264 / 0.10);
--shadow-lg:    0 8px 24px oklch(0.14 0.004 264 / 0.14);
--shadow-float: 0 16px 48px oklch(0.14 0.004 264 / 0.18);
```

- `--shadow-sm`: table rows on hover
- `--shadow-md`: cards, inline panels
- `--shadow-lg`: dropdowns, popovers
- `--shadow-float`: modals, dialogs

---

## 5. Component Conventions

**Interactive states (required on every interactive element):**
- `hover`: background shifts one step toward `--surface-inset`; cursor: pointer
- `active`: background shifts two steps; slight scale(0.98) transform
- `focus-visible`: 2px outline using `--action-primary` with 2px offset — visible in both light and dark themes; never removed, never replaced with box-shadow alone
- `disabled`: opacity 0.4; cursor: not-allowed; no pointer events
- `loading`: spinner or skeleton replaces content; button shows spinner inline

**Touch targets:** Minimum 44×44px for all interactive elements regardless of visual size. Use padding to expand hit area without changing the visual.

**Forms:**
- Label above the field, always — never placeholder-only labels
- Inline validation after blur, not on every keystroke
- Error text is `aria-describedby` linked to the input
- Error state: red border + error icon + error text below the field — never color alone
- Required fields marked with `*` and an `aria-required="true"` attribute

**Empty states:** Every list, table, and feed has a designed empty state with an illustration, a short explanation, and a call-to-action where appropriate.

**Loading states:** Skeleton screens that match the final layout beat a generic spinner. The skeleton uses `--surface-inset` as background with an animated shimmer.

**Error states:** State what failed ("Failed to load tasks") and what to do next ("Retry" button or a contact link). Never show a raw error code as the primary message.

---

## 6. WCAG Compliance Approach

The design system targets WCAG 2.1 AA as a minimum. Specific commitments:

- All text contrast ratios verified at AA or above (see §1)
- Focus indicators are visible and meet the WCAG 2.2 Focus Appearance criteria (minimum 2px, minimum contrast 3:1)
- Color is never the sole differentiator for state or status
- All images have `alt` text; decorative images use `alt=""`
- Form inputs are labeled and error messages are programmatically associated
- Keyboard navigation path is complete for all interactive flows
- Skip-to-main-content link provided in the page shell
- ARIA roles are used only where semantic HTML is insufficient; native elements preferred

**Limitation:** Full WCAG compliance requires manual testing with assistive technologies (VoiceOver, NVDA, JAWS) and user testing with disabled users. The design system provides the technical foundation; validation requires human review.

---

## 7. Dark Mode Strategy

Dark mode is planned as a future release feature. The token system is designed to support it from day one:

- All colors are semantic tokens (`--surface-base`, not `#f5f5f5`)
- The `[data-theme="dark"]` token set is defined in the design tokens file and applied via a `data-theme` attribute on `<html>`
- No component uses hardcoded color values
- Naive UI's `n-config-provider` accepts a custom theme that maps to the token set

When dark mode is activated, a user preference is saved to `localStorage` and synchronized to the backend user profile. The setting respects `prefers-color-scheme` by default.
