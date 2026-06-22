# PDD Reference: Frontend / UI Projects

> **Last reviewed**: 2026-04

Use this file to enrich Workflows 2, 3, and 5 for frontend and UI projects (React, Vue, Angular, Svelte, vanilla JS/TS, and related stacks).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- What UI framework and version? (React 18, Vue 3, etc.)
- Is there a design system or component library? (Tailwind, shadcn/ui, MUI, Chakra, custom)
- How is state managed? (useState, Zustand, Redux, Pinia, etc.)
- What are the routing and data-fetching patterns? (React Router, TanStack Query, SWR, etc.)
- Are there accessibility requirements? (WCAG level, screen reader support)
- What browsers and devices must be supported?
- Is there a Storybook or component sandbox?

**Design direction** — these prevent generic-looking output:

- What is the intended aesthetic tone? (brutally minimal, maximalist, retro-futuristic, editorial/magazine, luxury/refined, playful, brutalist/raw, organic/natural, art deco, industrial, soft/pastel — or describe your own)
- Are there specific brand fonts, or should the AI pick distinctive typography? (avoid defaulting to Inter/Roboto/Arial)
- What is the color strategy? (dominant color + sharp accents, monochrome, dark-first, specific palette)
- How should motion and animation be used? (page-load reveals, scroll-triggered, hover micro-interactions, restrained/none)
- What should make this interface memorable? (the one thing a user would remember)

### Extended `pdd/context/project.md` sections for frontend

```markdown
## UI / Design system
- Component library:
- Design tokens / theme:
- Storybook:

## Visual design direction
- Aesthetic tone: (e.g. brutalist, editorial, luxury, playful — not "clean and modern")
- Typography: display font + body font (avoid Inter/Roboto/Arial defaults)
- Color strategy: (dominant color, accent color, dark/light, specific palette)
- Motion approach: (staggered reveals, scroll-triggered, hover states, restrained)
- Memorable element: (the one thing a user remembers about this interface)

## State management
- Approach:
- Store structure:

## Data fetching
- Library:
- API base URL:
- Auth pattern:

## Browser / device targets
- Browsers:
- Minimum viewport:
- Accessibility standard: (e.g. WCAG 2.1 AA)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Frontend Conventions

## Component structure
- One component per file
- File name matches component name (PascalCase)
- Co-locate styles, tests, and stories with the component

## Naming
- Components: PascalCase (e.g. `UserCard.tsx`)
- Hooks: camelCase, prefixed with `use` (e.g. `useUserData.ts`)
- Utilities: camelCase (e.g. `formatDate.ts`)
- CSS classes: kebab-case or Tailwind utility classes only

## Props
- Define prop types explicitly — no implicit `any`
- Use interface for component props, type for unions/utilities
- Required props first, optional props last

## State
- Keep state as local as possible
- Lift state only when two+ siblings need it
- Global store only for truly app-wide state

## Side effects
- All data fetching in custom hooks or server components
- No fetch calls inside component render functions
- Loading, error, and empty states required for every async operation

## Styling
- [Tailwind utility classes / CSS modules / styled-components — pick one]
- No inline styles except for dynamic values
- Responsive: mobile-first breakpoints

## Accessibility
- All interactive elements must be keyboard-navigable
- ARIA labels required on icon-only buttons
- Color contrast ratio: 4.5:1 minimum
```

### Visual Design Conventions

```markdown
# Visual Design Conventions

## Typography
- Choose distinctive, characterful fonts — never default to Inter, Roboto, or Arial
- Pair a display font (headings) with a refined body font (text)
- Use CSS variables for font families so they can be swapped project-wide

## Color
- Define a dominant color and 1-2 sharp accent colors — avoid evenly distributed palettes
- Use CSS custom properties for all colors (no hardcoded hex in components)
- Dark/light mode: design one first, derive the other — don't treat both as afterthoughts

## Motion & Animation
- Prioritize high-impact moments: a well-orchestrated page load with staggered reveals
  creates more delight than scattered micro-interactions
- Use CSS animations where possible; reach for Motion/Framer only when CSS falls short
- Scroll-triggered and hover states should surprise, not just fade in

## Spatial Composition
- Break the grid intentionally — asymmetry, overlap, diagonal flow, grid-breaking elements
- Use generous negative space OR controlled density — avoid the mushy middle
- Avoid cookie-cutter card grids unless the content genuinely calls for them

## What to Avoid
- Generic "AI slop": purple gradients on white, system fonts, predictable card layouts
- Designs that look the same regardless of what the project is about
- Timid color choices — if the palette doesn't commit to something, it commits to nothing
- Motion for motion's sake — every animation should serve the aesthetic direction
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New component

```markdown
# Prompt: <ComponentName>

## Context
[Reference pdd/context/project.md — stack, design system, conventions]

## Design direction
- Aesthetic tone: <tone from project context — e.g. brutalist, editorial, playful>
- Typography: <display font + body font>
- Color: <dominant color, accent, dark/light>
- Motion: <specific animation approach for this component>
- What makes this component visually distinctive: <one sentence>

## Task
Create a <ComponentName> component that <does what>.

## Props
- `<propName>`: <type> — <description>
- `<propName>`: <type> (optional) — <description>

## Behavior
- <interaction or state behavior>
- <edge case: empty state, loading, error>

## Output format
Single `.tsx` file. Include:
- TypeScript prop types
- Component implementation
- Basic accessibility attributes
- No test file (separate prompt)

## Constraints
- Use [Tailwind / CSS modules] for styling
- No external libraries not already in package.json
- Must work at 320px minimum viewport width
```

### Data-fetching hook

```markdown
# Prompt: use<DataName>

## Task
Create a custom React hook `use<DataName>` that fetches <data> from <endpoint>.

## Returns
- `data`: <type | null>
- `isLoading`: boolean
- `error`: Error | null
- `refetch`: () => void

## Constraints
- Use [SWR / TanStack Query / fetch] — match existing pattern in codebase
- Handle loading, error, and empty states
- Include TypeScript return type
```

---

## Review Checklist (Workflow 5)

Apply these in addition to the universal review dimensions:

**Correctness**
- [ ] All prop types defined and correct?
- [ ] Loading, error, and empty states handled?
- [ ] No missing key props in lists?
- [ ] Event handlers cleaned up (useEffect cleanup)?

**UI / UX**
- [ ] Matches design system / component library conventions?
- [ ] Responsive at target viewports?
- [ ] No hardcoded colors or sizes that should be tokens?

**Accessibility**
- [ ] Interactive elements keyboard-navigable?
- [ ] ARIA labels on icon-only buttons?
- [ ] Form inputs have associated labels?
- [ ] Focus management correct for modals/dialogs?

**Performance**
- [ ] No unnecessary re-renders? (missing memo, useCallback where needed)
- [ ] Images have dimensions to prevent layout shift?
- [ ] No large dependencies imported for small utility use?

**Design quality**
- [ ] Typography is distinctive and intentional — not Inter/Roboto/Arial defaults?
- [ ] Color palette commits to a direction — no timid, evenly distributed pastels?
- [ ] Layout has spatial intent — not a generic card grid unless content requires it?
- [ ] Motion serves the aesthetic — animations feel designed, not default fade-ins?
- [ ] Overall aesthetic matches the stated design direction from context?
- [ ] Would a user remember this interface, or could it be any app?

**Code quality**
- [ ] Component does one thing?
- [ ] No business logic inside presentational components?
- [ ] Prop drilling more than 2 levels deep? (consider context or store)
