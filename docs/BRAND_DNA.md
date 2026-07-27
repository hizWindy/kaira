# Brand DNA v6

> **Precedence:** This file is the source of truth for design decisions in this brand. Where a generic tool, template, or AI agent default (Taste Skill, shadcn, Tailwind, Material, HIG defaults, etc.) conflicts with a rule stated here, this file wins — except where §16.1 explicitly concedes to platform-native convention.
>
> **Version:** v6 — 2026-07-10
> See §14 Changelog for history.
>
> **Validation status:** Calm register is battle-tested on web (SMS + fintech landing builds). Night register has one validated build (nightlife landing). Expressive and Editorial registers, cross-platform rules (§16), the Living Square (§1.2), the Spec Layer (§3.4), Illustration (§9.5), and Forms (§18) are drafted but not yet validated — treat as provisional until a real build tests them, then update per §14.

## Architecture: Invariants + Registers
This DNA is built in two layers:

- **Layer 1 — Invariant Core:** the things that make work recognizably this brand in *any* context. These never change: the signature element, the palette logic, the type-pairing logic, the motion character, the process machinery, and the philosophy of restraint. Sections §1–§13 define these.
- **Layer 2 — Context Registers (§17):** per-brief energy settings. A register changes how *loud* the work is allowed to be — dial ranges, which tools unlock — but never changes the identity. An expressive build and a calm build must still share visible DNA.

**Registers change energy, never identity.**

## Core DNA
Minimal, premium technology experiences that make complexity feel simple — expressed at different energy levels per context, never abandoned.

## Noticeable but subtle — what that means here
A loud brand shouts a logo at you. A subtle-but-noticeable brand gives you one small, precise detail that repeats everywhere without variation — you don't consciously clock it the first time, but by the fifth time you'd recognize a screenshot with the logo cropped out. Everything below is built around one such detail rather than several competing ones. Restraint is the point — and restraint is *relative to context*: a nightlife build is restrained compared to its neon competitors, even though it's louder than a fintech build.

As of v6, "noticeable but subtle" has three expressions, each in a different dimension so they never compete:
- **Shape:** the cut corner (§1) — the only shape signature
- **Behavior:** the living square (§1.2) — the only animated signature
- **Texture:** the spec layer (§3.4) — the only typographic flavor layer

One signature per dimension. Never two in the same dimension.

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
- **Reference signals:** Apple (behavioral restraint), Notion (plain language), Framer (motion with purpose), Teenage Engineering (precise geometric detail, spec-layer lineage)
- **Brand assets that always exist:** signature shape, palette logic, type pairing, motion character, icon style — defined below. New work extends these.
- **Mode:** greenfield or redesign (§12)
- **Platform:** web / iOS / Android / desktop (§16)

---

## 1. Signature Element — the cut corner *(invariant, all registers)*
**The decision:** every contained surface (card, button, modal, input) has one corner — top-left, always — cut at a hard 45° angle instead of rounded, sized to roughly half the standard radius. A single small square of the accent color sits exactly in that cut, at a fixed size per container type.

Why this works as "noticeable but subtle":
- It costs nothing in usability — it reads as "rounded card" at a glance.
- It's rare — uniform radius is the default everywhere, which is why one broken corner stands out on close inspection.
- It's cheap to apply consistently — one clip-path (or native shape), one fixed accent square.
- It scales from favicon to hero card without a second signature.

**Rule:** this is the only shape signature, in every register. Registers may change how loud everything *around* it is; the signature itself never varies.

---

## 2. Color *(logic invariant; exact values are the default palette)*

### Default palette
| Color | Hex | Role |
|---|---|---|
| Foundation | `#f7fcfc` | Clean base, light surfaces |
| Depth | `#061414` | Premium depth and authority, dark surfaces |
| Accent | `#97b833` | Growth, action, energy — and the signature mark |
| Neutral | `#8A9A98` | Balance and subtlety |

---

## 3. Typography *(pairing logic invariant; faces are the default)*

**Default faces:** Bricolage Grotesque (UI) + Merriweather (voice) + JetBrains Mono (utility: code and the spec layer).

---

## Rules
1. Remove before adding
2. Simplicity over decoration
3. Clarity over complexity
4. Motion with purpose
5. Premium through restraint — restraint measured relative to context
6. One signature per dimension — shape, behavior, texture — applied everywhere, without exception
7. Identity converges across platforms; mechanics follow each platform's conventions
8. Registers change energy, never identity
