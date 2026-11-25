# Warden Design System — Clean (Attio / folk inspired)

## Overview

Warden's UI is a clean, modern SaaS operations console in the style of Attio and folk: white space, subtle borders, clean shapes, and small, quiet typography. Nothing shouts. The interface gets out of the way so the runs, traces, gates, and evals do the talking. This replaces the earlier RawBlock (brutalist) direction, which did not suit this product.

**Attio rebuild (2026-11-25):** the first "clean" pass only polished Warden v1 (a font swap and renamed tokens) and did not adopt Attio's components. This version rebuilds the components themselves from the Attio home screenshot: the sectioned sidebar with a search box and a Getting started pill, the top bar with a breadcrumb and Help, the time-aware greeting, and the big "Ask anything…" box for starting a run. Warden's content (runs, traces, gates, evals, quests, memory) is unchanged — only the components presenting it are Attio's. See "Attio components" below and the screenshot map in `assets/ui-refactor-attio/README.md`.

---

## Colors

- **Ink** (#111111): Headings, primary text
- **Body** (#333333): Body text
- **Muted** (#6B7280): Secondary text, captions, placeholders
- **Faint** (#9CA3AF): Tertiary text, hints
- **Paper** (#FFFFFF): App background, card background
- **Wash** (#FAFAFA): Sidebar background tint (the main content area is paper white, like Attio's)
- **Border** (#E5E7EB): Hairline borders, dividers, input borders
- **Border strong** (#D1D5DB): Borders on hover / emphasis
- **Teal** (#0D9488, sculk teal): Warden accent — active states, links, key highlights, the logo motif. Used sparingly, never as a large fill.
- **Success** (#16A34A): Success text / dot (soft green)
- **Warning** (#D97706): Warning text / dot (soft amber)
- **Error** (#DC2626): Error text / dot (soft red)
- **Info** (#2563EB): Info links
- **Tint success** (#F0FDF4), **tint warning** (#FFFBEB), **tint error** (#FEF2F2), **tint teal** (#F0FDF9): Pale badge/chip backgrounds

## Typography

- **Headline Font**: Manrope (clean geometric sans; Inter was flagged by Impeccable as overused)
- **Body Font**: Manrope
- **Mono Font**: A clean monospace for ids, timings, costs, and code (JetBrains Mono)

- **h1**: 28px semibold, 1.2 line height (page titles — calm, not oversized)
- **h2**: 20px semibold, 1.3 line height
- **h3**: 16px semibold, 1.4 line height
- **body**: 14px regular, 1.6 line height
- **small**: 13px regular, 1.5 line height
- **tiny**: 12px regular, 1.4 line height (captions, metadata)
- **mono**: 13px regular, 1.5 line height

Note: Inter is on Impeccable's overused list — Manrope is the chosen clean sans. It still reads as the Attio/folk style; the clean, quiet look wins over font novelty.

## Spacing

Base unit: 4px. Generous whitespace is the look — airy sections, roomy cards, clear separation.
- **sp-1**: 4px
- **sp-2**: 8px
- **sp-3**: 12px
- **sp-4**: 16px
- **sp-5**: 24px
- **sp-6**: 32px
- **sp-7**: 48px
- **sp-8**: 64px

Layout: sidebar ~220px, content max-width ~1100px, section gaps 24–32px, card padding 20–24px.

## Border Radius

Clean shapes, softly rounded — the opposite of sharp.
- **radius-sm** (6px): Small badges, chips, inputs
- **radius-md** (8px): Buttons, cards
- **radius-lg** (12px): Large inputs, prominent cards, modals
- **radius-pill** (999px): Status badges, filter chips, avatars, toggle pills

## Elevation

Almost flat. Hierarchy comes from spacing, weight, and tint — not depth.
- **shadow-none**: Most elements (cards use a hairline border instead)
- **shadow-sm** (0 1px 2px rgba(0,0,0,0.05)): Cards on hover, dropdowns, modals
- **shadow-md** (0 4px 12px rgba(0,0,0,0.08)): Modals, popovers only

## Components

### Buttons
#### Primary
black (#111111) fill, white text, 8px radius, 1px black border. 14px medium. Hover: #000000. Used for the one main action per view.
#### Secondary
white fill, ink text, 1px border (#E5E7EB), 8px radius. Hover: border strong + wash background.
#### Ghost
transparent, muted text, no border, 8px radius. Hover: wash background, ink text.
#### Destructive
error (#DC2626) fill, white text, 8px radius. Hover: darker red.
#### Accent (sparingly)
teal (#0D9488) fill, white text, 8px radius. Only for the single most important action where the Warden brand should show (e.g. starting a run).
#### Sizes
Small (6px 12px, 13px, 32px), Medium (8px 16px, 14px, 36px), Large (10px 20px, 15px, 44px).
#### Disabled State
wash fill, faint text, 1px border (#E5E7EB). No opacity tricks.

### Cards
#### Default
white fill, 1px border (#E5E7EB), 8px radius, no shadow. 20–24px padding.
#### Interactive
same, plus hover shadow-sm and border strong.
#### Section header
16px semibold ink title + 13px muted subtitle, 16px gap below.

### Inputs
white fill, ink text, 1px border (#E5E7EB), 8px radius (12px for large search/ask inputs). 14px. 10px/14px padding. Placeholder muted.
- **Hover**: border strong.
- **Focus**: 1px teal border + soft teal ring (0 0 0 3px rgba(13,148,136,0.12)), outline none.
- **Error**: 1px error border.
- **Disabled**: wash background, faint text.
#### Label
13px medium ink, 6px margin-bottom. Sentence case, not uppercase.
#### Helper Text
12px muted. 6px margin-top.

### Chips / Badges
#### Status Badge
pill (999px), 11–12px medium, 4px/10px padding. Tinted background + matching darker text + no border (or a 1px tinted border).
- **Success**: #F0FDF4 bg, #16A34A text.
- **Warning**: #FFFBEB bg, #D97706 text.
- **Error**: #FEF2F2 bg, #DC2626 text.
- **Neutral**: #F3F4F6 bg, #4B5563 text.
- **Teal**: #F0FDF9 bg, #0D9488 text.
#### Filter Chip
white fill, body text, 1px border (#E5E7EB), pill. 6px/12px padding, 13px. Active: black fill, white text.

### Lists / Tables
- Row: 1px bottom border (#F3F4F6), 12–16px vertical padding. Hover: wash background.
- Header: 12px medium muted, uppercase, letter-spacing 0.04em.
- No trailing icons unless they do something; text first.

### Sidebar
- Width ~220px, wash (#FAFAFA) background, 1px right border (#E5E7EB).
- Logo row at the top (Warden mark + name + tagline), then the search box.
- **Search box** (Attio): white, 1px hairline border, 8px radius, magnifier icon on the left, "Search" placeholder, ⌘K hint on the right. Typing filters the nav items; ⌘K / Ctrl+K focuses it; Escape clears it.
- **Nav, grouped into sections** (Attio's Records/Lists/Chats pattern): the main group is unlabeled (Dashboard, Runs, Approvals); the data views sit under a small muted section label, **Records** (Evals, Agents & quests, Memory), which is collapsible (chevron, open by default).
- Nav item: 14px, body text, 16px icon (Lucide, 1.5px stroke), 8px radius, 8px/12px padding. Hover: #F3F4F6 background. Active: #F3F4F6 background + ink text + ink icon + medium weight (no heavy black block). The Approvals item carries a soft amber pill with the pending count.
- **Dashed "+ New run" button** below the nav (Attio's "+ New list" / "+ New chat"): 1px dashed border, muted text; opens the Runs view with the new-run form already open.
- **Getting started pill** at the bottom (Attio's "Getting started 1/6"): white pill, 1px hairline border, "Getting started" + a real `n/6` count + a 2px teal progress bar. The six steps are real — run a run, review an approval, save a memory, run the eval suite, complete a quest, connect the live backend — derived from the backend where possible and from local actions otherwise (`lib/gettingStarted.ts`). Clicking it goes to the Dashboard.
- Bottom: small "getting started" pill and muted footer text ("2 agents connected" + one quiet line).

### Top bar
- 48px tall, white, 1px bottom border. Left: a breadcrumb — small Home icon + the page name ("Home" on the Dashboard, otherwise the view name). Right: a quiet Help action (HelpCircle icon + "Help", links to the repo) and the Live/Demo backend badge. The big page title lives in the content now, not in this bar.

### Greeting + AskBox (Dashboard home)
- The Dashboard opens like Attio's home: a large time-aware greeting as the page title — "Good morning/afternoon/evening, Saad." (28px semibold) — then the big **AskBox**.
- **AskBox**: a large rounded box (12px radius, white, 1px hairline border, teal focus ring) with a 3-row textarea ("Ask anything…", 15px) and a bottom-right row: the agent picker ("Auto" by default — Scout; or Scout / Planner), a Slash button that opens starter task templates, a Mic button for voice dictation (shown only when the browser supports speech recognition), and a teal send button (ArrowUp, white on teal #0D9488 — Warden's brand in place of Attio's light blue). Enter sends; Shift+Enter is a newline. Sending calls the real run-creation path (`api.createRun`) and opens the new run's detail page — it is the primary way to start a run.
- **Suggestion chips** below the box, centered (Attio's "Prep for next meeting" chip): pill, 1px hairline border, small Calendar icon + label ("Research a vendor", "Update the CRM", "Draft a vendor brief"). Clicking one fills the box with that task and focuses it.

### Section headers
- Attio's "Meetings" / "Tasks 0" row: a 16px semibold ink title on the left, a quiet muted meta note or a small action ("View all") on the right (`SectionHeader` in `ui.tsx`). Used on the Dashboard to group Reliability, Cost & failure modes, and Recent runs; other views use a 20px semibold in-content title + a muted subtitle line instead of the old 28px header-bar title.

### Icons
- **Library: Lucide only (`lucide-react`, already installed). No other icon set, no emoji as UI.**
- **Style, everywhere: thin outline, `strokeWidth={1.5}`, rounded caps/joins (Lucide default).**
- **Sizes:** 16px (`h-4 w-4`) for nav and button icons; 18px (`h-[18px] w-[18px]`) for section/action icons (e.g. the approval-gate warning); 14px (`h-3.5 w-3.5`) for small inline icons (chips, table status, trace steps).
- **Colors:** muted (#6B7280) by default; ink (#111111) when active (nav) or emphasized; a status color only where the icon carries a status (amber warning, green pass, red fail, teal brand accent). Never use the Lucide default 2px stroke.
- **Choices — match Attio's icon for the equivalent concept:**
  | Warden element | Lucide icon | Why |
  |---|---|---|
  | Dashboard (sidebar + breadcrumb) | `Home` | Attio's Home icon |
  | Runs | `Activity` | run history / activity |
  | Approvals | `CheckSquare` | Attio's Tasks icon |
  | Evals | `FlaskConical` | lab / eval suite |
  | Agents & quests | `Trophy` | leaderboard / quests |
  | Memory | `Brain` | stored knowledge |
  | Sidebar search | `Search` | magnifier, like Attio's search box |
  | Top-bar Help | `HelpCircle` | Attio's Help |
  | AskBox | `Mic`, `Slash`, `ArrowUp` (send) | Attio's ask-box row |
  | Suggestion chips | `Calendar` | Attio's "Prep for next meeting" chip icon |
  | "+" actions | `Plus` | Attio's "+ New list / + New chat" |
  | Section collapse | `ChevronDown` | Attio's section chevrons |
  | Agents connected (footer) | `Bot` | the agents |
  | Run trace steps | `GitBranch` (node), `Wrench` (tool), `Brain` (LLM/memory), `TriangleAlert` (gate) | step type |
  | Approve / Reject | `Check` / `X` | decision |
  | Replay trace | `RotateCcw` | replay |
  | Verify trace / Re-run for real | `RotateCcw` / `Zap` | static verification vs actual re-execution |
  | Live streaming indicator | `Radio` | the run is producing steps over SSE |
  | Back | `ArrowLeft` | back |
  | Close (modal) | `X` | close |
  | Demo-mode badge | `FlaskConical` | demo / mock data |
- Audit rule: every `<Icon … />` in the app carries an explicit `strokeWidth={1.5}`. The one exception is the Sparkline's SVG polyline (`strokeWidth={2}`), which is a chart line, not an icon.
- Not adopted: Attio's date navigation (`ChevronLeft` / `ChevronRight` beside "Yesterday, Sep 1"). Warden has no date-based view to navigate — the Dashboard trend is a static "Last 7 eval windows" label — so adding prev/next arrows would be decoration, not function.

### Empty states
Centered, 14px muted text + a 13px muted sub-line + one clear action button. Generous vertical padding (48–64px). No illustration.

## Do's and Don'ts

1. **Do** use whitespace and tint to create hierarchy; the page should breathe.
2. **Don't** use thick borders, sharp corners, or heavy black blocks — that was the old direction.
3. **Do** keep text small and quiet: 14px body, 12–13px secondary, muted grays for anything that isn't the point.
4. **Don't** use more than one accent per view; teal is the brand accent and it should appear sparingly.
5. **Do** use pill badges and soft tints for status — a status should read at a glance.
6. **Don't** add decorative images or illustrations; content and typography do the work.
7. **Do** make the primary action obvious (one black button per view) and everything else quiet.
8. **Do** keep the sidebar narrow and calm; it is navigation, not content.
9. **Don't** overuse uppercase — reserve it for tiny section labels and table headers.
10. **Do** match Attio/folk: if a choice looks like it belongs in a clean CRM, it's right; if it looks like a poster, it's wrong.
