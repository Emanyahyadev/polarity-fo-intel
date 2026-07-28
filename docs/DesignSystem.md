# Design System — the Intelligence Workspace UI

The customer-facing UI (`src/fointel/serve/web/index.html`) is an **intelligence
workspace** for capital allocators, not a chatbot. Every element exists to improve
clarity, trust, or speed; anything decorative was removed. This document specifies the
system so another engineer can extend it consistently.

**Honest scope.** The workspace only surfaces what the verified dataset actually
contains. Features that would require data we do not have (relationship graphs,
portfolio analytics, collaboration) are deliberately absent — a fake feature would
violate the same no-fabrication standard the dataset is built on.

## 1. Identity

A **private-bank ledger** aesthetic: calm paper surfaces, ink neutrals hue-biased
toward a deep *ledger green* accent, monospace for figures. Deliberately not
SaaS-blue, not AI-purple, not a chat UI. The brand mark is a bar-chart monogram in a
rounded frame — registry, measurement, restraint.

## 2. Design tokens (CSS custom properties)

| Token | Light | Dark | Role |
|---|---|---|---|
| `--paper` | `#F7F8F6` | `#111514` | page ground |
| `--surface` | `#FFFFFF` | `#181D1B` | cards, panels |
| `--ink / ink2 / ink3` | `#151C18 / #46524C / #75817B` | `#E6EAE7 / #A7B2AB / #7A857F` | text hierarchy |
| `--line / line2` | `#E5E9E4 / #D2D9D2` | `#262D2A / #343C38` | hairlines / interactive borders |
| `--accent` | `#17604A` | `#58BA92` | ledger green — actions, brand, meters |
| `--ok` | `#116B3F` | `#5CBE8C` | verified / High confidence |
| `--warn` | `#96570A` | `#D9A050` | Medium confidence / abstention |
| `--cite` | `#1A56A8` | `#7AA7DE` | links, sources, 13F signals |

Semantic mapping: **confidence** High=ok, Medium=warn, Low=neutral; **verification
chips** carry a small `--ok` dot; **abstention** is first-class warn styling, never an
error state; **retrieval match** uses the accent. All text/background pairs meet WCAG
AA at their used sizes.

Theming is token-level: `prefers-color-scheme` sets the default; the topbar toggle
stamps `data-theme` on the root (persisted in `localStorage`), which overrides the
media query in both directions.

## 3. Typography

- **UI**: Inter (400/500/600/700), `-webkit-font-smoothing: antialiased`.
- **Data**: IBM Plex Mono for AUM figures, dates, ids, evidence quotes, citations —
  terminal precision without a terminal aesthetic; `font-feature-settings: "tnum"`
  wherever digits align.
- Scale: display 24/1.25 · section 15/650 · body 14.5/1.58 · meta 13 · micro-labels
  11.5px uppercase, +0.07em tracking, 600.
- Body copy is width-capped (`max-width: 68ch`) for long research sessions.
- Fonts load from Google Fonts with `display=swap`; the system stack is the fallback,
  so the page is fully usable if the CDN is unreachable.

## 4. Spacing, shape, elevation

4-px base scale (4/8/12/16/20/24/32/48). Radii: 6 chips · 10 cards · 12 panels · 999
pills. Elevation is nearly flat: `0 1px 2px rgba(12,22,17,.05)` resting, one soft hover
step — trust reads as restraint, not depth.

## 5. Layout

Sticky topbar (brand · Research/Directory tabs · live record count from `/health` ·
theme toggle · `/` hint). Content grid `minmax(0,1fr) 292px`: a centred 860-px research
column and a rail with **Session** (recent queries), **Pinned records**, and **Dataset
coverage** — the coverage bars are computed live by `/stats` from the records the
service is actually answering from, so the panel can never disagree with the data. The
rail collapses below 1100 px.

## 6. Answer anatomy (trust-first)

1. **Verdict strip** — "Answered — grounded in N verified records" or "Declined —
   insufficient verified evidence", plus a mode chip whose tooltip states exactly how
   the answer was produced: *Synthesized · grounded* (LLM, post-verified), *Deterministic
   extract* (verified fields only; also the honest degradation when the LLM free-tier
   daily quota is exhausted), or *Declined*.
2. **Executive summary** — LLM prose as paragraphs; extractive output parsed into
   scannable rows (never a wall of text).
3. **Record cards** — name (linked) · type + confidence badges · facts grid
   (location / AUM / principal / phone) · retrieval-match meter · verification chips +
   `data_as_of` freshness · recent 13F activity rows · expandable **Evidence &
   classification** (the exact qualifying evidence) · Pin / Copy-citation actions.
4. **Retrieval footnote** — method + the cited `fo_id`s in mono.

Uncertainty is never hidden: Undetermined types get a neutral badge, missing fields
render as absent (not invented), and the abstention path is styled as a designed
outcome.

## 7. Directory

A sortable, filterable table of every served record (`/records`): name, type,
location, AUM (numeric-aware sort), confidence; row-click expands an inline detail
(principal, phone, website, freshness, verification, signals, evidence). Client-side
CSV export of exactly what is on screen. 55 rows need no virtualization — noted here so
scale-up work knows where the ceiling is.

## 8. Motion

One curve (`cubic-bezier(.2,.7,.3,1)`), one duration token (170 ms). Entrances: 5-px
rise + fade, cards staggered 45 ms. Skeleton shimmer during retrieval. Expanders animate
via the details marker rotation. Hover: border + 1-px lift. Everything is disabled
under `prefers-reduced-motion`.

## 9. Interaction & accessibility

- **Keyboard-first**: `/` focuses search from anywhere, `Enter` asks, `Esc` clears;
  tabs, chips, pins, and actions are real `<button>`s; `:focus-visible` shows a 2-px
  accent ring.
- Landmarks (`header/main/aside/footer`), `role=tablist/tab/tabpanel`,
  `aria-live=polite` results, `aria-pressed` pins, labelled inputs, `th[scope=col]`.
- Copy actions confirm via a toast (`role=status`).

## 10. Serving contract

The UI is a single self-contained file consuming four read-only endpoints —
`/health`, `/stats`, `/records`, `POST /query` — with no build step, no framework, and
no state beyond `localStorage` (recent queries, pins, theme). Presentation stays fully
separated from retrieval/grounding, which live in `fointel.rag`.
