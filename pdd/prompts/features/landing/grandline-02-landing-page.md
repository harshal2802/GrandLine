# Prompt: Landing Page
**File**: pdd/prompts/features/landing/grandline-02-landing-page.md
**Created**: 2026-04-04
**Project type**: Full-stack (Next.js frontend)
**Issue**: #3

## Context
GrandLine is a multi-agent orchestration platform themed after One Piece. The Next.js 14 App Router frontend is scaffolded under `src/frontend/` with Tailwind CSS and an ocean color palette already configured. The landing page is SSG (static site generation) — no backend dependency.

### Existing setup
- Next.js 14 with App Router at `src/frontend/`
- Tailwind CSS with custom `ocean` color palette (50-950)
- Root layout at `app/layout.tsx` with dark ocean-950 background
- Placeholder page at `app/page.tsx` (will be replaced)
- Framer Motion needs to be added as a dependency

### The Crew (for crew section)
| Agent | Role | One-liner |
|---|---|---|
| Captain | Project Manager | Decomposes tasks into voyage plans |
| Navigator | Architect | Drafts Poneglyphs (PDD prompts) |
| Shipwrights | Developers | Build code following Poneglyphs |
| Doctor | QA Engineer | Writes tests before code (TDD) |
| Helmsman | DevOps | Deploys across three tiers |

### The Pipeline (for pipeline section)
PDD → TDD → Implement → Review → Deploy

### Observation Deck views (for preview section)
- Sea Chart (Board View) — tasks flowing through pipeline stages
- Crew Map (Graph View) — live DAG of agent communication
- Ship's Log (Timeline View) — chronological agent actions

## Task
Replace the placeholder `app/page.tsx` with a fully designed, responsive SSG landing page that establishes the GrandLine product identity with One Piece theming and smooth Framer Motion animations.

## Input
- Existing Next.js 14 app with Tailwind + ocean color palette
- One Piece vocabulary and crew definitions from context

## Output format
Files to create/modify under `src/frontend/`:

```
app/page.tsx                          — Full landing page (SSG)
components/landing/Hero.tsx           — Hero section
components/landing/CrewSection.tsx    — 5 crew member cards
components/landing/PipelineSection.tsx — Voyage pipeline visualization
components/landing/ObservationDeckPreview.tsx — 3 view previews
components/landing/Footer.tsx         — Footer with tagline
components/landing/Navbar.tsx         — Fixed top nav
```

## Sections (top to bottom)

### 1. Navbar (fixed)
- GrandLine logo/wordmark on left
- Navigation links: Crew, Pipeline, Observation Deck, GitHub
- "Chart a Course" CTA button (links to `/app` — disabled for now, shows tooltip "Coming soon")
- Transparent on scroll top, solid ocean-900 on scroll

### 2. Hero
- Large heading: "Assemble your crew. Navigate the GrandLine."
- Subheading: "A multi-agent orchestration platform where AI agents voyage through a disciplined pipeline to build, test, and deploy software."
- "Get Started" CTA button
- Subtle animated background (CSS gradient animation or particles — keep it lightweight)
- Framer Motion fade-in + slide-up on load

### 3. Crew Section
- Section title: "The Crew"
- 5 cards in a responsive grid (3 cols on desktop, 1 on mobile)
- Each card: agent name, role title, one-line description, themed icon or emoji
- Framer Motion staggered fade-in on scroll

### 4. Pipeline Section
- Section title: "The Voyage Pipeline"
- Horizontal flow visualization: PDD → TDD → Implement → Review → Deploy
- Each stage is a styled node/card connected by arrows or lines
- Brief description under each stage
- "PDD and TDD aren't optional — they're the Log Pose." tagline below
- Framer Motion: stages animate in sequence left-to-right on scroll

### 5. Observation Deck Preview
- Section title: "The Observation Deck"
- 3 preview cards: Sea Chart, Crew Map, Ship's Log
- Each card: view name, description, placeholder visual (styled div or abstract illustration)
- "Watch the voyage unfold in real time." tagline
- Framer Motion fade-in on scroll

### 6. Footer
- "Assemble your crew. Navigate the GrandLine."
- Links: GitHub, Docs, API Reference
- Copyright

## Constraints
- SSG — no `"use client"` on the page itself. Client components only for interactive pieces (navbar scroll, animations)
- Framer Motion components must be marked `"use client"`
- Responsive: mobile-first, looks good at 320px through 1440px+
- Dark nautical theme using the ocean color palette
- No external images — use CSS/SVG/emoji for visuals
- Lighthouse SEO score ≥ 90 (proper meta tags, semantic HTML, heading hierarchy)
- No `any` types in TypeScript
- Keep animations performant — no layout thrashing, use `transform` and `opacity`
- Install `framer-motion` as a dependency

## Acceptance Criteria
- [ ] Landing page renders at `/` with all 6 sections
- [ ] All 5 crew members displayed with roles
- [ ] Pipeline visualization shows all 5 stages with connections
- [ ] 3 Observation Deck views previewed
- [ ] Framer Motion animations smooth on scroll (staggered reveals)
- [ ] Navbar transitions from transparent to solid on scroll
- [ ] Responsive layout works at 320px, 768px, 1024px, 1440px
- [ ] Semantic HTML (proper heading hierarchy, nav, main, footer, section)
- [ ] No TypeScript errors, no `any` types
- [ ] Page is SSG — `next build` produces static HTML
