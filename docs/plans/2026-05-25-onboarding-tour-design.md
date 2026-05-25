# Onboarding Tour — Design Spec

**Date:** 2026-05-25
**Status:** Approved by user, ready for implementation plan.
**Goal:** Show a 4-step spotlight tour on first launch so new users immediately understand what Git Archiver does and how to use it. Replayable from Settings.

---

## Why

The app's core flows (add URL → background clone → automatic archive → manual or scheduled update) are obvious once you've used it for a minute, but invisible on first launch — the user sees an empty table and an unexplained search bar. A short interactive tour collapses the discovery curve from minutes to ~30 seconds.

---

## Format & UX

- **Spotlight overlay** (dimmed background + tooltip that points to a real UI element).
- **4 steps**, single forward-only "Next" button per step, "Skip tour" always available.
- Plays automatically on first launch only. Persists a "completed" flag so it never re-plays unbidden.
- User can replay it any time from the Settings dialog.

---

## Architecture

### State

A new Zustand store (`useTourStore`) holds the live tour state:

```ts
interface TourStore {
  tourActive: boolean;
  tourStepIndex: number;
  startTour(): void;   // resets index, clears completion flag, sets active true
  endTour(): void;     // sets active false, writes localStorage flag
  advance(): void;     // tourStepIndex++ (driven by Joyride's callback)
}
```

**Persistence:** A single localStorage key `git-archiver-tutorial-completed` (string `"true"` or absent). Set on tour completion or skip. Read once on App mount to decide whether to auto-start the tour. We do NOT use Zustand's `persist` middleware here — the flag's lifecycle is too simple (write once, read on mount) and the existing `task-store` already owns the only `persist` instance we want.

### Component layout

```
App
├── ThemeProvider
│   └── … existing tree …
│   └── <OnboardingTour />   ← new, mounts a single <Joyride />
└── <Toaster />
```

- `<OnboardingTour />` is a thin wrapper. Reads `tourActive` and `tourStepIndex` from the store; subscribes to `useRepoStore` to decide whether to include step 3 (skipped on empty list). Defines the static `steps` array. Passes everything to `<Joyride>` from `react-joyride`.
- `<Joyride>` portals its DOM to `<body>`, so it sits above existing Radix dialogs/menus. No z-index wars.

### Trigger logic

In `App.tsx`'s existing mount-time `useEffect`:

```ts
useEffect(() => {
  repoStore.fetchRepos();
  settingsStore.fetchSettings();
  if (localStorage.getItem("git-archiver-tutorial-completed") !== "true") {
    useTourStore.getState().startTour();
  }
}, []);
```

### Replay path

A new "Help" section at the bottom of the SettingsDialog with one button:

```
Show tutorial again →  (clicking it)
  - calls onOpenChange(false)  // close SettingsDialog
  - setTimeout(() => useTourStore.getState().startTour(), 200)
                                            ↑ wait for Radix close animation
```

---

## The 4 steps

| # | Target selector | Title | Body | Placement |
|---|----------------|-------|------|-----------|
| 1 | `body` (centered) | **Welcome to Git Archiver** | Track GitHub repositories and automatically snapshot them as compressed `.tar.xz` archives whenever they change. This quick tour takes 30 seconds. | `center` |
| 2 | `[data-tour-id="add-repo-bar"]` | **Add a repository** | Paste a GitHub URL (`https://github.com/owner/repo`) here and click Add. The app will clone the repo and create your first archive automatically. | `bottom` |
| 3 | `[data-tour-id="row-actions"]` | **Per-repo actions** | The `⋯` menu on each row lets you view archives, retry failed clones, copy the URL, or remove a repo. Status updates appear in the table as background tasks run. | `left` |
| 4 | `[data-tour-id="settings-button"]` | **Settings** | Add a GitHub token (raises the API rate limit from 60 to 5,000/hour), schedule daily syncs, or change where clones are stored. You can replay this tour from here anytime. | `bottom-end` |

**Step 3 is conditionally dropped** when `useRepoStore.getState().repos.length === 0` at tour-start time. (First-launch case: only steps 1, 2, 4 are shown. Replay case: all 4 if any repos exist.)

### Joyride config

- `continuous: true` — single Next button (vs. per-step button arrays)
- `showSkipButton: true` on every step
- `disableScrolling: false` — auto-scroll the spotlight into view
- `styles.options.primaryColor`: pull `--primary` from the existing Tailwind CSS variable so dark/light theme switches just work
- `locale: { last: "Got it" }` — change the last step's "Last" → "Got it"
- `disableCloseOnEsc: false` — Esc is treated as Skip

---

## Files

### New

- `src/stores/tour-store.ts` (~40 lines including types)
- `src/components/onboarding-tour.tsx` (~80 lines)
- `src/stores/__tests__/tour-store.test.ts` (~50 lines, 4 tests)

### Modified

| File | Change | Lines |
|------|--------|-------|
| `src/App.tsx` | Mount `<OnboardingTour />`, add startTour() conditional in existing useEffect | +5 |
| `src/components/add-repo-bar.tsx` | `data-tour-id="add-repo-bar"` on outer div | +1 |
| `src/components/app-header.tsx` | `data-tour-id="settings-button"` on the settings cog | +1 |
| `src/components/repo-table/row-actions.tsx` | `data-tour-id="row-actions"` on the menu trigger | +1 |
| `src/components/dialogs/settings-dialog.tsx` | New "Help" section with "Show tutorial again" button | +20 |
| `src/__tests__/app.test.tsx` | Extend: tour auto-starts when flag unset; doesn't when set | +30 |

### Dependency

- `react-joyride@^2.9.x` — `pnpm add react-joyride`. React 19 compatible.

---

## Error handling & edge cases

- **localStorage write failure** (private browsing, quota): `endTour()` wraps the `localStorage.setItem` in try/catch and logs the failure. Tour was still completed (state is reset); next launch will replay the tour. Mildly annoying but not broken.
- **Targeted element missing** (e.g., AddRepoBar hidden in some future variant): Joyride handles this gracefully — it skips the step with a console warning. The tour continues.
- **Tour started but the row-actions step is included, then the user deletes all repos mid-tour**: extremely unlikely (the user can't interact with the table while the spotlight is active), but defensible — Joyride will detect the missing target and skip.
- **Theme change mid-tour**: Joyride re-reads its `styles` prop each render, so the tooltip recolors live. No special handling needed.
- **Window resize mid-tour**: Joyride re-positions automatically.

---

## Testing

| Test | File | What it asserts |
|------|------|-----------------|
| `startTour resets state` | `stores/__tests__/tour-store.test.ts` | `startTour()` flips `tourActive=true`, resets `tourStepIndex=0`, removes `localStorage.git-archiver-tutorial-completed`. |
| `endTour persists flag` | `stores/__tests__/tour-store.test.ts` | `endTour()` flips `tourActive=false`, writes `localStorage.git-archiver-tutorial-completed = "true"`. |
| `advance increments index` | `stores/__tests__/tour-store.test.ts` | `advance()` increments `tourStepIndex` by 1. |
| `endTour handles localStorage failure` | `stores/__tests__/tour-store.test.ts` | Mock `localStorage.setItem` to throw; assert `tourActive` still flips to false. |
| `App auto-starts tour when flag unset` | `__tests__/app.test.tsx` | Mount with localStorage empty → `useTourStore.getState().tourActive === true`. |
| `App skips auto-start when flag set` | `__tests__/app.test.tsx` | Mount with localStorage `git-archiver-tutorial-completed = "true"` → `tourActive === false`. |

End-to-end interaction tests (clicking Next, dismissing) are deferred to manual smoke testing — Joyride's own behavior is already covered by upstream tests, and DOM-querying its internal portal is brittle.

---

## YAGNI / out of scope

- **Per-step interactive validation** ("now type a URL!") — too rigid; the user might want to read all four steps without committing to an action.
- **A11y voice-over walkthrough** — Joyride already manages focus + aria-labels; no extra layer.
- **Tour for the SettingsDialog itself** (sub-tour for sync schedule, token, etc.) — would be a second tour; not in scope for v1.
- **Analytics on tour completion** — no telemetry framework in the app today.
- **Backend persistence of the completion flag** — localStorage is adequate; not worth a DB migration for a single bool.

---

## Acceptance

User accepts when, against a fresh app data dir:

1. Launching the app shows the welcome step centered, dimmed background, single "Next" button + "Skip tour" link.
2. Clicking through reaches step 2 (AddRepoBar spotlight), step 4 (Settings cog spotlight — step 3 is skipped because no repos).
3. Clicking "Got it" on step 4 dismisses the tour and the next launch does NOT replay.
4. Opening Settings → "Help" → "Show tutorial again" closes Settings, briefly waits, then re-launches the tour from step 1.
5. After adding a repo, replaying the tour shows all 4 steps including the row-actions step.
6. Theme switch mid-tour: tooltip color follows the theme.
