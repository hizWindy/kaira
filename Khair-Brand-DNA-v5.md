# Brand DNA v5

> **Precedence:** This file is the source of truth for design decisions in this brand. Where a generic tool, template, or AI agent default (Taste Skill, shadcn, Tailwind, Material, HIG defaults, etc.) conflicts with a rule stated here, this file wins — except where §16.1 explicitly concedes to platform-native convention.
>
> **Version:** v5 — 2026-07-07
> See §14 Changelog for history.
>
> **Validation status:** Calm register is battle-tested on web (SMS + fintech landing builds). Night register has one validated build (nightlife landing). Expressive and Editorial registers, and the cross-platform rules (§16), are drafted but not yet validated — treat as provisional until a real build tests them, then update per §14.

## Architecture: Invariants + Registers
This DNA is built in two layers:

- **Layer 1 — Invariant Core:** the things that make work recognizably this brand in *any* context. These never change: the signature element, the palette logic, the type-pairing logic, the motion character, the process machinery, and the philosophy of restraint. Sections §1–§13 define these.
- **Layer 2 — Context Registers (§17):** per-brief energy settings. A register changes how *loud* the work is allowed to be — dial ranges, which tools unlock — but never changes the identity. An expressive build and a calm build must still share visible DNA.

**Registers change energy, never identity.**

## Core DNA
Minimal, premium technology experiences that make complexity feel simple — expressed at different energy levels per context, never abandoned.

## Noticeable but subtle — what that means here
A loud brand shouts a logo at you. A subtle-but-noticeable brand gives you one small, precise detail that repeats everywhere without variation — you don't consciously clock it the first time, but by the fifth time you'd recognize a screenshot with the logo cropped out. Everything below is built around one such detail rather than several competing ones. Restraint is the point — and restraint is *relative to context*: a nightlife build is restrained compared to its neon competitors, even though it's louder than a fintech build.

## Personality
- Intelligent
- Modern
- Calm (register-relative: composed, never chaotic — even at high energy)
- Intentional
- Helpful
- Growth-oriented → expressed through progress/momentum moments (§5.1)

---

## 0. Brief (read this before generating anything)
- **Page/product kind:** websites, apps, and product demos across verticals — tech/dev, fintech, nightlife/events, entertainment, apparel/lifestyle, and beyond
- **Audience:** stated per brief — the audience picks the register, not personal taste
- **Register (required):** declare one of Calm / Night / Expressive / Editorial (§17) before generating. If the brief doesn't obviously map to one, state the choice and the reasoning in one line.
- **Vibe words:** per register — see §17
- **Reference signals:** Apple (behavioral restraint), Notion (plain language), Framer (motion with purpose), Teenage Engineering (precise geometric detail)
- **Brand assets that always exist:** signature shape, palette logic, type pairing, motion character, icon style — defined below. New work extends these.
- **Mode:** greenfield or redesign (§12)
- **Platform:** web / iOS / Android / desktop (§16)

### 0.1 Design dials
Dial *ranges* are set by the declared register (§17.1). The invariant rule: whatever the register, the dials are declared before generating and every layout/motion/density decision is gated by them. Generic tool defaults (e.g. 8/6/4) never apply.

---

## 1. Signature Element — the cut corner *(invariant, all registers)*
**The decision:** every contained surface (card, button, modal, input) has one corner — top-left, always — cut at a hard 45° angle instead of rounded, sized to roughly half the standard radius. A single small square of the accent color sits exactly in that cut, at a fixed size per container type.

Why this works as "noticeable but subtle":
- It costs nothing in usability — it reads as "rounded card" at a glance.
- It's rare — uniform radius is the default everywhere, which is why one broken corner stands out on close inspection.
- It's cheap to apply consistently — one clip-path (or native shape), one fixed accent square.
- It scales from favicon to hero card without a second signature.

**Rule:** this is the only shape signature, in every register. Registers may change how loud everything *around* it is; the signature itself never varies.

### 1.1 Implementation rules
- **Accent square sizing:** 6px badges/tags, 8px buttons/inputs, 10px cards/modals — never larger than the cut.
- **Nesting:** only the outer container in a stack carries the cut; inner elements use plain rounded corners.
- **RTL:** the cut stays top-left regardless of text direction.
- **Dark surfaces:** verify the accent square against both Foundation and Depth; adjust opacity only, never color.
- **Compact scaling:** under 480px (or compact size class), cut sizes step down one tier (14 → 10, 8 → 6); accent squares proportionally. Never omitted, only scaled.
- **Platform rendering:** see §16.2.

---

## 2. Color *(logic invariant; exact values are the default palette)*

### 2.0 Palette logic (the invariant)
Every project has exactly: one light surface, one dark surface, one accent, one neutral — with semantic states derived from the accent's hue family so they never look imported from another brand. The default palette below serves most briefs; if a client project requires different hues, the *structure* (4 roles + derived semantics + all usage rules) is non-negotiable.

### Default palette
| Color | Hex | Role |
|---|---|---|
| Foundation | `#f7fcfc` | Clean base, light surfaces |
| Depth | `#061414` | Premium depth and authority, dark surfaces |
| Accent | `#97b833` | Growth, action, energy — and the signature mark |
| Neutral | `#8A9A98` | Balance and subtlety |

### Semantic colors (derived from the accent hue)
| State | Hex | Notes |
|---|---|---|
| Success | `#6E9A2E` | Darker, desaturated step from accent |
| Warning | `#B8912E` | Same profile, shifted warmer |
| Danger | `#B85A2E` | Muted brick-orange, not alarm red |

### Usage rules *(invariant)*
- Surfaces dominate. Accent appears only for: the signature mark, primary CTAs, active/selected states, and live/progress indicators.
- Accent and neutral are **fill colors, not text colors**.
- Semantic colors are fills/badges/icons only, with a darker text-safe variant for labels on their own tint.

### 2.1 Color Consistency Lock *(invariant, mandatory)*
Once the accent is applied, it's the only accent across the entire page/flow. One palette per project.

### 2.2 Accessibility & contrast *(invariant)*
- Depth-on-Foundation (and inverse) is the only body-copy pairing — WCAG AA (>4.5:1).
- Accent/Neutral never as text.
- Focus states: visible 2px Accent ring, 2px offset — never color-only.
- The signature is decorative — never the sole indicator of state or interactivity.

### 2.3 Surface direction & dark mode
- **Default (Calm/Expressive/Editorial):** Foundation is the base surface; Depth is reserved for weighty moments. Dark mode follows the OS setting (`prefers-color-scheme`, system appearance APIs) and inverts the pair — no third palette.
- **Dark-first inversion (Night register, §17.3):** when night *is* the product's context, Depth becomes the base surface and Foundation becomes the rare, weighty inversion. Same pair, same rules, inverted default. This is a register-level decision declared in the brief — never an ad-hoc per-section choice.
- If a manual theme toggle is offered, it's offered on all platforms or none.
- Contrast and hierarchy hold parity in both modes.

---

## 3. Typography *(pairing logic invariant; faces are the default)*

**Pairing logic (the invariant):** one grotesque carries all UI and body text; one serif is reserved for rare "voice" moments — empty states, onboarding welcomes, testimonials/quotes — so the shift registers as the product speaking personally, not a competing typeface.

**Default faces:** Bricolage Grotesque (UI) + Merriweather (voice). Client projects may substitute faces; the pairing logic and the three-moments restriction are non-negotiable.

**Type rules:**
- Two weights only per font
- Large size jump between headline and body (Editorial register may push this further, §17.5)
- Sentence case everywhere
- No em dashes in shipped copy

### 3.1 Voice examples
- **Empty state:** "Nothing here yet. Your first project will show up in this space."
- **Onboarding:** "Good to have you here. Let's get your first thing set up."
- **Testimonial label:** "In their own words —"

### 3.2 Font delivery & fallbacks
- Self-host on web; bundle as app fonts on native (confirm embedding license).
- UI fallback: `system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif`. Voice fallback: `Georgia, 'Times New Roman', serif`.
- `font-display: swap` on web — brief system-font flash is acceptable; invisible text is not.

### 3.3 Text scaling
- Type responds to system text-size settings on every platform (Dynamic Type, Android font scale, browser zoom via rem).
- Headline size caps at 1.5× base under scaling; body continues to grow.
- Never fixed px for text on web.

---

## 4. Corner Radius *(invariant)*
- Base radius 10px (or platform equivalent) on all rounded corners
- The signature cut is the one exception — ~14px cards/modals, ~8px buttons/inputs
- No pill shapes anywhere, in any register

---

## 5. Layout
- 8pt spacing scale, without exception *(invariant)*
- Single primary content column, defined max-width *(Calm/Night default; Expressive and Editorial may break the single column per §17 — deliberately, not by default)*
- Whitespace as the default state, scaled per register's VISUAL_DENSITY range
- Full-bleed and inverted-surface sections: reserved for weighty moments in Calm; more freely available in other registers per §17

### 5.1 Growth-oriented moments
- Progress indicators, milestones, momentum states use a small animated fill in Accent or the strand mark advancing.
- Strand mark confirmed uses: progress fills, route/step connectors, live-level indicators (crowd, capacity, load). It is a *linear measure* mark — don't use it decoratively.

### 5.2 Breakpoints & size classes
| Tier | Web | Native | Behavior |
|---|---|---|---|
| Compact | < 480px | compact width class | Signature steps down one tier, nav collapses |
| Medium | 480–960px | tablet portrait | Full-size signature, single column at max-width |
| Expanded | > 960px | tablet landscape / desktop | Content capped at 960px (Calm/Night); Expressive/Editorial may use wider stages per §17 |

---

## 6. Inspiration *(behavioral principles, not visual references)*
| Reference | Principle | Maps to |
|---|---|---|
| Apple | Restraint — remove until it breaks, then add one back | §1, §13 |
| Notion | Plain language, one idea at a time | §7 |
| Framer | Motion with purpose | §8 |
| Teenage Engineering | Precise geometric detail, restrained palette, point of view | §1 |

**Guardrail:** if output starts resembling Apple's actual look, the reference has drifted from principle to surface — pull back.

---

## 7. Communication DNA *(invariant)*
- Explain simply · Remove unnecessary words · One idea at a time · Short, understandable messaging

Instead of: *"Leveraging innovative systems for digital transformation"*
Prefer: *"Building systems that solve real problems."*

Register note: copy energy may rise with the register (Night/Expressive copy can be punchier), but never at the cost of clarity, and never into hype-speak.

---

## 8. Interaction DNA
- **Motion character *(invariant)*:** decisive, no bounce, no overshoot, no lingering. Motion confirms; it never performs for its own sake — even in Expressive, where there is simply *more* of it, not a different character.
- **Web:** `cubic-bezier(0.4, 0, 0.2, 1)` — 150ms micro, 250ms surface. Expressive register adds a 400ms step for orchestrated reveals (§17.4). No other curves.
- **Native:** critically-damped springs (§16.3) — damping never below 1.0.
- Hover/pressed: border/background/opacity shifts — not scale or shadow (Expressive may use small translate, §17.4)
- **Loading:** fade-in only — no skeleton shimmer, no bouncing dots, any register.

---

## 9. Iconography *(invariant)*
- Outline style, 1.5px stroke at 24px, scaling proportionally
- Standard rounded joints — no cut-corner treatment on icons
- Depth/Foundation default; Accent only for active/selected

---

## 10. Imagery & Photography *(register-dependent — see per-register rules in §17)*
Baseline (Calm/Night):
- Single duotone/overlay derived from Foundation + Depth — no third color via imagery
- 4:5 portraits, 16:9 screenshots
- Screenshots never get the cut-corner treatment
- No generic stock; real screenshots, real work, or palette-derived abstract shapes

Editorial register **overrides** the duotone rule (§17.5) — photography leads there, and strangling it into two colors would defeat the register's purpose. Expressive sits between: imagery may be full-color but must be palette-harmonized in grading.

---

## 11. Logo & Mark *(invariant)*
- Signature mark: cut-corner + accent-square motif, standalone-capable
- Wordmark: name in the UI face bold, mark left, clear space = mark width
- Minimums: mark ≥16px; lockup ≥20px mark height
- Monochrome: Depth-on-Foundation or inverse only — never Accent alone

### 11.1 Favicon / app icons
- 32/16px grids, mark only; at 16px drop unresolvable detail
- App icons: design the mark centered on full-bleed Foundation or Depth and let the OS apply its own mask — don't fight platform icon shapes

---

## 12. Redesign / Audit Mode *(invariant)*
1. Audit first — document current state before changing anything
2. Preserve slugs, anchor IDs, analytics event names
3. Never regress existing accessibility wins
4. Apply the DNA incrementally, flagging SEO/tracking conflicts before changes

---

## 13. Anti-Slop / Banned List
### 13.1 Absolute bans *(every register, no exceptions)*
- A second signature shape or motif alongside the cut corner
- Pill-shaped buttons or tags
- Purple/blue AI-default gradients; any gradient outside the project's palette family
- Default shadcn/Tailwind/Material styling shipped without passing through the token system
- Glassmorphism
- Bouncing, overshooting, or infinite-loop animations
- Em dashes in shipped copy
- More than two typefaces (UI + voice)
- Accent or neutral as body text
- Cut-corner treatment on icons, images, or OS-native chrome

### 13.2 Register-gated tools *(banned in Calm; unlocked per §17)*
| Tool | Calm | Night | Expressive | Editorial |
|---|---|---|---|---|
| Dark-first base surface | ✗ | ✓ (core rule) | ✗ | ✗ |
| Scroll-triggered reveal | ✗ | ✗ | ✓ once per page | ✓ once per page |
| Scale/translate hover | ✗ | ✗ | ✓ small translate only | ✗ |
| Multi-column / broken-grid layout | ✗ | ✗ | ✓ deliberate | ✓ deliberate |
| Full-color photography | ✗ (duotone) | ✗ (duotone) | ✓ palette-harmonized | ✓ leads the design |
| Oversized display type (>1.5× scale jump) | ✗ | ✗ | ✓ | ✓ |
| Warning/live-state colors as UI indicators | sparingly | ✓ | ✓ | sparingly |

---

## 14. Changelog & Versioning
- **v5 — 2026-07-07:** Two-layer architecture: invariant core + Context Registers (§17: Calm/Night/Expressive/Editorial). Register field required in Brief. Banned list split into absolute vs register-gated (§13). Dark-first inversion documented as the Night register's core rule (§2.3), retroactively legitimizing the nightlife build. Palette and type pairing restated as invariant *logic* with default values, enabling client-project substitution without losing structure. Strand-mark use cases codified (§5.1). Imagery rules made register-dependent (§10).
- **v4 — 2026-07-07:** Cross-platform system (§16), font fallbacks, text scaling, dark-mode mechanism, breakpoint table, app-icon masking, motion restated as character + per-platform implementation
- **v3 — 2026-07-07:** Iconography, imagery, logo/lockup, favicon, redesign mode, a11y, mobile scaling, voice examples, precedence header
- **v2 — 2026-07-07:** Brief/dials, signature implementation gaps, Color Consistency Lock, growth rule, loading rule, banned list, pre-flight
- **v1:** Original Brand DNA

---

## 15. Pre-Flight Check
- [ ] **Register declared in the brief, and every unlocked tool used is permitted by that register (§13.2 / §17)**
- [ ] Exactly one corner (top-left) carries the cut, correct size for container/viewport/platform
- [ ] Accent square present at fixed size, verified on both surfaces
- [ ] No nested double-cut in any visual stack
- [ ] Body text confined to the approved surface pairing
- [ ] Motion matches the stated character — correct curve/springs, register-appropriate intensity, no bounce anywhere
- [ ] Voice font only in its three approved moments
- [ ] One accent across the entire page/flow
- [ ] No absolute-ban item present (§13.1)
- [ ] Base radius 10px except the cut; no pills
- [ ] Focus visible and not color-only
- [ ] Icons outline, 1.5px, no cut
- [ ] Imagery follows the declared register's rules (§10/§17)
- [ ] Touch targets meet platform minimums (§16.4)
- [ ] OS-native chrome unbranded (§16.1)
- [ ] Type responds to system scaling with headline cap
- [ ] Safe areas respected; no signature on window chrome

---

## 16. Cross-Platform System
*Status: provisional until validated by a native build.*

### 16.1 The brand/platform boundary
The signature and tokens apply to **brand-owned surfaces** (cards, buttons, inputs, modals, custom components). **OS-native chrome stays native and unbranded**: nav bars, tab bars, back gestures, pull-to-refresh, share sheets, permission dialogs, context menus. Test: "would a user expect this to behave identically in every app?" If yes → native, unbranded.

### 16.2 Signature corner per platform
Invariant is the idea (one 45° cut, top-left, accent square) — not the rendering math.
- **Web:** CSS `clip-path` (validated)
- **iOS:** custom SwiftUI `Shape`/`CAShapeLayer` — straight bevel + three native continuous corners
- **Android:** Compose `GenericShape` or MaterialShapeDrawable cut-corner (Material supports cut corners natively — easiest platform)
- **Desktop:** web-tech shells identical to web; native toolkits follow the iOS/Android principle
- Minor per-platform differences in the rounded corners are accepted; the cut and square are pixel-intentional everywhere.

### 16.3 Motion translation
Character invariant: quick, decisive, no bounce.
- **Web:** the stated bezier at 150/250ms (+400ms Expressive step)
- **iOS:** critically-damped springs — `.spring(response: 0.25, dampingFraction: 1.0)` surfaces, `0.15` micro. Damping never below 1.0.
- **Android:** Material standard/decelerate easing tokens at matching durations — never the overshoot curves.
- Rule of thumb: platforms may *look* slightly different in side-by-side video; they must never *feel* different.

### 16.4 Touch targets vs. visual size
- Minimums: 44×44pt iOS, 48×48dp Android, 44×44px web/desktop touch.
- Small visuals get invisible expanded hit areas — never enlarge the visual to fix a target, never shrink a target to match a visual.
- Mouse-precise desktop controls may be smaller only if unreachable by touch.

### 16.5 Safe areas & window chrome
- Mobile: all layouts respect safe-area insets; full-bleed color extends into them, content and controls do not.
- Desktop: the signature never appears on the window frame/title bar — the window is the OS's, the content is the brand's.

### 16.6 Platform parity rule
Visual identity converges across platforms; interaction mechanics follow each platform's conventions.

---

## 17. Context Registers
*Status: Calm validated (2 builds). Night validated (1 build). Expressive and Editorial are provisional.*

A register is declared per brief (§0) and sets the energy envelope. It never changes the invariant core (§1–§13.1).

### 17.1 Dial ranges per register
| Register | DESIGN_VARIANCE | MOTION_INTENSITY | VISUAL_DENSITY |
|---|---|---|---|
| Calm | 3–4 | 2–3 (cap 4 growth moments) | 2–3 |
| Night | 3–5 | 3–4 | 3–4 |
| Expressive | 5–7 | 5–6 | 3–5 |
| Editorial | 4–6 | 2–3 | 4–6 |

### 17.2 Calm *(default)*
- **For:** SaaS, dev tools, fintech, portfolios, professional products
- **Vibe words:** calm, intentional, precise, human tech
- **Rules:** the v4 ruleset exactly — Foundation base, single column, hover-only motion, duotone imagery. When in doubt about register, Calm is the answer.

### 17.3 Night
- **For:** nightlife, bars/clubs, events, music, late-context products
- **Vibe words:** confident, composed after dark, precise — never neon-hype
- **Core rule — dark-first inversion:** Depth is the base surface; Foundation becomes the rare weighty moment (§2.3). Declared at the brief level, applied to the whole product.
- **Unlocks:** live/status indicators in Accent, warning-family colors for capacity/urgency states, slightly denser cards.
- **Stays banned:** pulsing/glowing "live" effects (static dots only), neon gradients, glassmorphism.
- **Positioning note:** in a vertical drowning in neon, composed-dark reads as the premium option — the restraint *is* the differentiation.

### 17.4 Expressive *(provisional)*
- **For:** entertainment, campaigns, launches, motion-design showcases, creative-studio work
- **Vibe words:** bold, orchestrated, deliberate spectacle
- **Unlocks:** one scroll-triggered orchestrated reveal per page (400ms step, same curve family); oversized display type; broken-grid/asymmetric layouts (the cut corner remains the only *shape* irregularity — layout asymmetry is composition, not a second signature); small translate on hover; full-color palette-harmonized imagery.
- **Hard limits:** motion still never bounces or loops; one orchestrated moment per page, not per section — spectacle is spent in one place, like boldness; every Absolute Ban holds.
- **Test:** an Expressive page should feel like this brand *performing*, not a different brand.

### 17.5 Editorial / Imagery-first *(provisional)*
- **For:** apparel, fashion, lifestyle, food, photography-led brands
- **Vibe words:** curated, art-directed, quiet confidence
- **Core rule — photography leads:** the duotone rule is lifted; imagery runs full-color with palette-harmonized grading (no filter that fights the palette; UI chrome around imagery stays strictly in-palette so the system frames the photography rather than competing with it).
- **Unlocks:** denser image grids, editorial multi-column layouts, oversized display type, per-art-direction crop ratios.
- **Hard limits:** UI components (buttons, cards, nav) follow every invariant — the cut corner frames the content; motion stays Calm-level (fashion reads premium through stillness); every Absolute Ban holds.
- **Test:** remove the photography and the remaining UI skeleton should be unmistakably this system.

### 17.6 Choosing a register
- The **audience and product context** pick the register — never personal preference for louder or quieter.
- If a brief seems to need two registers, it's one register with a weighty-moment exception — pick the dominant one.
- If a brief needs energy beyond Expressive's ceiling (full spectacle, chaotic maximalism), that's outside this DNA: use the process machinery (§0, §13, §15) with a project-specific token system, and say so explicitly rather than stretching the brand past recognition.

---

## Rules
1. Remove before adding
2. Simplicity over decoration
3. Clarity over complexity
4. Motion with purpose
5. Premium through restraint — restraint measured relative to context
6. One signature, applied everywhere, without exception
7. Identity converges across platforms; mechanics follow each platform's conventions
8. Registers change energy, never identity
