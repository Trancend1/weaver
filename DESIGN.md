# Design System: Weaver Cockpit

## 1. Visual Theme & Atmosphere

A restrained, cockpit-dense translation workbench — like a scholar's desk lamp illuminating aged manuscript paper. The atmosphere is warm and purposeful: ink on parchment, rendered in software. Every surface is slightly warm (never cold or blue-grey), every shadow carries a faint amber tint rather than black. Density is high (8/10) because this is a professional tool, not a showcase. Variance is low (3/10): the layout is predictable, hierarchical, information-first. Motion is minimal (2/10): only functional state transitions — no decorative choreography.

The design language maps to a Japanese publishing atelier: disciplined grid, warm neutrals, deliberate use of subtle accent. The single accent color (forest green) is reserved exclusively for "progress" and "healthy" states — never used decoratively.

## 2. Color Palette & Roles

- **Vanilla Canvas** (`#faf9f6`) — App background, page surface
- **Milk White** (`#ffffff`) — Cards, inputs, modals — pure clean white
- **Warm Panel** (`#fffefc`) — Panels, dropdowns — white with faintest amber warmth
- **Raised Fill** (`#f6f5f1`) — Table headers, pressed button states, secondary fills
- **Disabled Track** (`#eeece5`) — Disabled inputs, progress track backgrounds
- **Warm Border** (`#e5e2da`) — Default structural borders (warm, never cold)
- **Inner Divider** (`#f0eee8`) — Softer inner rule lines, table row separators
- **Deep Ink** (`#1a1712`) — Deepest text — page titles, headings — near-black with brown undertone
- **Ink Primary** (`#211c15`) — Body copy, interactive labels — primary readable text
- **Ink Dark** (`#44403a`) — Secondary copy, descriptions, labels
- **Muted Taupe** (`#6f6a61`) — Secondary metadata, placeholder labels
- **Whisper Gray** (`#9b968c`) — Ghost text, faint stats, disabled labels
- **Amber Link** (`#7a4f18`) — Hyperlinks, clickable navigation
- **Gold Focus** (`#9b6a24`) — Focus rings, hover accent borders
- **Ethereal Gold** (`#c79a4a`) — Decorative rule highlights (thin, 1px only)
- **Forest Green** (`#1f7a4a`) — Single accent: progress, "ok", translated states, primary action buttons
- **Amber Warn** (`#9a5b13`) — Warning states: pending review, conflicts
- **Brick Red** (`#b03a28`) — Error / bad states: failed jobs, missing files
- **Steel Blue** (`#44607f`) — Info states: job details, neutral notifications
- **Parchment Reader** (`#f4efe5`) — Background for reading preview / epub viewer surfaces
- **Cream Tint** (`#faf6ee`) — Selected card highlight, focus tint backgrounds
- **Cream Divider** (`#ece2d1`) — Decorative fill dividers in dense panels
- **Parchment Hairline** (`#e4dac8`) — Hairline separators in the reader pane

Shadows always use warm amber tint: `rgb(63 45 22 / 0.07–0.10)` — never neutral gray, never black.
No neon. No purple. No cool grays. Palette stays warm-neutral throughout.

## 3. Typography Rules

- **UI / Interface:** IBM Plex Sans — geometric-humanist grotesque, technical authority. Track-tight for headings (`-0.025em`), neutral for body (`0`). Weight hierarchy: 400 / 550 / 650 / 750. IBM Plex Sans reads like it belongs in a tool, not a landing page.
- **Reader Preview:** IBM Plex Serif — only inside the reading preview / epub viewer template. Never in dashboard or cockpit UI. Relaxed leading (`1.72`). Max-width `65ch`.
- **Monospace:** JetBrains Mono — code snippets, segment IDs, technical metadata, stats numbers at high density. All numeric data in dense tables uses monospace to prevent layout jumping.
- **Scale:** 12px (xs) · 14px (sm) · 16px (base) · 18px (md) · 22px (lg) · 28px (xl). Base body text: `15px/1.5`.
- **Banned fonts:** Inter (too generic), system-ui for UI labels, any generic serif (Times New Roman, Georgia, Garamond) in cockpit context.
- **Caps labels:** Small-caps style with `tracking-caps: 0.04em` — used for section headers, column headers, metadata tags.

## 4. Component Stylings

- **Primary Buttons:** `background: #211c15` (deep ink), `color: #ffffff`, `border-radius: 8px` (radius-md), `height: 40px`, tactile `-1px translateY` on `active`. No outer glow. No neon shadow. Hover: `background: #3a3127`. Forest green variant for key creation/import actions.
- **Secondary / Ghost Buttons:** Transparent background, `border: 1px solid #e5e2da`, `color: #211c15`. Hover: `background: #f6f5f1`. Quiet — does not compete with primary.
- **Destructive Buttons (sm only):** `color: #b03a28`, `border: 1px solid rgb(180 35 24 / 0.4)`. Only appears in contextual menus, not as top-level CTAs.
- **Cards (Project Grid):** `border-radius: 12px` (radius-lg), `background: #ffffff`, `border: 1px solid #e5e2da`, shadow: `0 1px 0 rgb(255 255 255 / 0.75) inset, 0 10px 26px rgb(63 45 22 / 0.07)` — the inset white creates a subtle top-edge highlight (engraved feel). Cards use warm tint `background: #f6f5f1` on hover. Error cards use `inset 3px 0 0 #b03a28` left-edge accent.
- **Panels:** `background: #fffefc`, `border-radius: 16px` (radius-xl), shadow: `0 1px 0 rgb(255 255 255 / 0.82) inset, 0 18px 42px rgb(63 45 22 / 0.08)`. Used for sidebar, content sections.
- **Progress Bars:** Native `<progress>` element styled as thin warm-tinted track. Value fill: `#1f7a4a`. Track: `#eeece5`. Height: 6px.
- **Badges / Status Pills:** Pill shape (`border-radius: 9999px`), semantically colored: `ok` = green fill, `warn` = amber fill, `bad` = red fill, `info` = steel-blue fill. All fills at 10% opacity with 1px border at 28% opacity.
- **Inputs / Textareas:** `border: 1px solid #e5e2da`, `border-radius: 8px`, `background: #ffffff`, `height: 40px`. Label always above. Error text below in `#b03a28`. Focus ring: `outline: 2px solid #9b6a24`. No floating labels.
- **Sidebar Items:** Left-edge active indicator (3px inset): `background: rgba(245, 240, 230, 0.7)` on hover, active uses forest green left border. Full-width, touch-safe `44px` minimum height.
- **Segment Editor Rows:** Alternating fills for translated/untranslated. In-progress rows use pulsing left indicator. `id="seg-{id}"` anchors must remain (HTMX dependency).
- **Loaders / Skeletons:** Warm shimmer matching layout dimensions — `background: linear-gradient(90deg, #f6f5f1, #faf6ee, #f6f5f1)`. No spinners. No generic circular loaders.
- **Empty States:** Composed: icon (SVG, not emoji) + title + hint text + optional CTA. Background: `#f4efe5`. Never just "No data found" with no context.
- **Error Fragments (Q2b pattern):** Inline `<div class="error" role="alert">` with brick-red left border. Appears in-place within the HTMX swap target, not as a modal.

## 5. Layout Principles

Fixed topbar (`56px`) + optional sidebar (`264px` expanded / `56px` collapsed) + main content area. Max content width `1160px` (standard), `1480px` (wide tables/workspace). Sidebar sits on the left; collapsible. Top bar holds brand + primary navigation.

Two layout modes: `layout--global` (dashboard, no project selected) and `layout--project` (project-scoped: sidebar shows project tree). A third mode `layout--workspace` collapses the project tree sidebar. These modes control sidebar behavior via CSS class only — no JavaScript required for the shell layout.

Grid is CSS Grid throughout. No `calc()` percentage hacks. Spacing scale: 4px / 8px / 12px / 16px / 24px / 32px / 48px. Component padding always from the scale — never arbitrary values.

For the Project Grid (Dashboard): 3-column responsive grid at `1fr 1fr 1fr` above 1024px, 2-column at 640px–1024px, 1-column below 640px. Cards never equal-height forced — let natural content flow.

HTMX anchor IDs (`#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#qa-badge-status`, `#qa-issues`, `id="seg-{id}"`, `qa-badge-vol-*`, `qa-badge-ch-*`) are structural invariants — never rename.

## 6. Motion & Interaction

Transitions: `140ms ease` for background, border-color, color. No spring physics in a dense cockpit tool — transitions should feel immediate and functional, not bouncy. Buttons respond in under 100ms. HTMX swaps should be instant by default.

Only exceptions: loading skeletons use a slow shimmer (`2s` infinite `ease-in-out`), and job progress bars animate width smoothly (`300ms ease`). All animation via `transform` and `opacity` exclusively — never `top`, `left`, `width`, `height`.

No perpetual micro-animations on static dashboard elements. A professional tool is not a marketing page.

## 7. Anti-Patterns (Banned)

- **No emojis** — never in templates, buttons, labels, or copy
- **No Inter** — IBM Plex Sans is the chosen UI font; Inter is generic
- **No generic serifs** (Times New Roman, Georgia, Garamond) — IBM Plex Serif only in reader preview
- **No pure black** (`#000000`) — always warm near-black: `#1a1712` or `#211c15`
- **No cool grays** — never Zinc/Slate/neutral palettes in this project; always warm brown-gray
- **No neon or outer-glow shadows** — shadows always warm-amber tinted at 7–10% opacity
- **No purple accent** — no purple-blue gradient buttons, no "AI purple" anywhere
- **No over-saturated accents** — forest green at `#1f7a4a` is the only accent; never increase saturation
- **No gradient text** on headings — weight and color hierarchy instead
- **No centered Hero sections** — dashboard is data-first, not marketing
- **No 3-equal-column card rows** for features — project grid uses context-adaptive sizing
- **No AI copywriting** ("Seamless", "Elevate", "Next-Gen", "Intelligent", "AI-powered")
- **No custom mouse cursors**
- **No CDN fonts or external assets** — all fonts loaded locally or system-stack only
- **No `h-screen`** — use `min-h-[100dvh]` for full-height sections
- **No modal-only error reporting** — errors render inline as fragments via `role="alert"`
- **No raw SQL in UI routers** — all data via `services/` functions
- **No source-file hashing on render paths** — Q2 hardening rule; overview uses DB-only reads
- **No provider calls, QA scans, or progress computation on dashboard/list render**
- **No global mutable store** — cross-project data from `workspace_index` (read-only) only
- **No broken `picsum.photos` or fake avatar links** — use SVG initials or existing static assets
- **No sparkle / wand / magic icons** for AI-assist features — plain function labels only
