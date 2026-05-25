# Onboarding Tour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 4-step first-launch spotlight tour using react-joyride, persisted by a single localStorage flag, replayable from the Settings dialog.

**Architecture:** A small Zustand store (`useTourStore`) holds live tour state. A single `<OnboardingTour />` component mounts at the App root and wraps `<Joyride>`. On App mount, an existing `useEffect` reads localStorage and calls `startTour()` if the user hasn't completed the tour. The SettingsDialog gets a "Help" section with a "Show tutorial again" button that resets the flag and re-triggers the tour. Three targeted components (AddRepoBar, AppHeader settings cog, row-actions menu) get stable `data-tour-id` attributes so Joyride can find them by selector.

**Tech Stack:** React 19, TypeScript, Zustand (`create` only — no `persist` middleware here), `react-joyride@^2.9.x`, Vitest + @testing-library/react.

**Spec:** `docs/plans/2026-05-25-onboarding-tour-design.md`

---

## Setup

### Setup-1: Confirm workspace state and install react-joyride

**Files:** none (dependency add)

- [ ] **Step 1: Verify clean baseline**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git status
```

Expected: on `main`, working tree clean (or only contains in-progress unrelated changes that should be set aside before this work).

- [ ] **Step 2: Install react-joyride**

```bash
cd git-archiver-v2
pnpm add react-joyride
```

Expected: a line like `+ react-joyride 2.9.x` in the output. The dependency lands in `package.json` and `pnpm-lock.yaml`.

- [ ] **Step 3: Run the baseline tests to confirm nothing regressed**

```bash
pnpm test --run
```

Expected: 138/138 tests pass (the count before the tour work begins). If anything fails, stop — fix the baseline before continuing.

- [ ] **Step 4: Commit the dependency add**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git add git-archiver-v2/package.json git-archiver-v2/pnpm-lock.yaml
git commit -m "chore(deps): add react-joyride for onboarding tour"
```

---

## Task 1: Tour store

The store is the source of truth for tour state. We build it test-first because its public API (`startTour`, `endTour`, `advance`, `tourActive`, `tourStepIndex`) is what every other piece of this feature depends on. Following the codebase's existing pattern (see `src/stores/task-store.ts`) we use Zustand `create` without `persist` middleware — we manage the one localStorage flag manually since its lifecycle is too simple to need the middleware.

**Files:**
- Create: `git-archiver-v2/src/stores/tour-store.ts`
- Test: `git-archiver-v2/src/stores/__tests__/tour-store.test.ts`

- [ ] **Step 1: Write the four failing tests**

Create `git-archiver-v2/src/stores/__tests__/tour-store.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTourStore, TUTORIAL_COMPLETED_KEY } from "../tour-store";

describe("useTourStore", () => {
  beforeEach(() => {
    // Reset store state and localStorage between tests
    useTourStore.setState({ tourActive: false, tourStepIndex: 0 });
    localStorage.clear();
  });

  it("startTour activates the tour, resets the index, and clears the completion flag", () => {
    localStorage.setItem(TUTORIAL_COMPLETED_KEY, "true");
    useTourStore.setState({ tourStepIndex: 3 });

    useTourStore.getState().startTour();

    expect(useTourStore.getState().tourActive).toBe(true);
    expect(useTourStore.getState().tourStepIndex).toBe(0);
    expect(localStorage.getItem(TUTORIAL_COMPLETED_KEY)).toBeNull();
  });

  it("endTour deactivates the tour and persists the completion flag", () => {
    useTourStore.setState({ tourActive: true, tourStepIndex: 2 });

    useTourStore.getState().endTour();

    expect(useTourStore.getState().tourActive).toBe(false);
    expect(localStorage.getItem(TUTORIAL_COMPLETED_KEY)).toBe("true");
  });

  it("advance increments the step index by 1", () => {
    useTourStore.setState({ tourActive: true, tourStepIndex: 0 });

    useTourStore.getState().advance();
    expect(useTourStore.getState().tourStepIndex).toBe(1);

    useTourStore.getState().advance();
    expect(useTourStore.getState().tourStepIndex).toBe(2);
  });

  it("endTour still deactivates the tour when localStorage.setItem throws", () => {
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("QuotaExceededError");
      });
    useTourStore.setState({ tourActive: true });

    expect(() => useTourStore.getState().endTour()).not.toThrow();
    expect(useTourStore.getState().tourActive).toBe(false);

    spy.mockRestore();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd git-archiver-v2
pnpm test --run src/stores/__tests__/tour-store.test.ts
```

Expected: FAIL — module `../tour-store` not found.

- [ ] **Step 3: Implement the store**

Create `git-archiver-v2/src/stores/tour-store.ts`:

```ts
import { create } from "zustand";

/** localStorage key tracking whether the user has finished or skipped the tour. */
export const TUTORIAL_COMPLETED_KEY = "git-archiver-tutorial-completed";

export interface TourStore {
  tourActive: boolean;
  tourStepIndex: number;
  /** Reset index, clear completion flag, mark tour active. Called on App mount
   * for first-time users and from the "Show tutorial again" Settings button. */
  startTour: () => void;
  /** Mark tour inactive and persist the completion flag. Survives localStorage
   * write failures (private browsing / quota) by logging and continuing. */
  endTour: () => void;
  /** Move to the next step. Driven by Joyride's step:after callback. */
  advance: () => void;
}

export const useTourStore = create<TourStore>((set) => ({
  tourActive: false,
  tourStepIndex: 0,

  startTour: () => {
    try {
      localStorage.removeItem(TUTORIAL_COMPLETED_KEY);
    } catch (err) {
      console.warn("Failed to clear tutorial flag from localStorage", err);
    }
    set({ tourActive: true, tourStepIndex: 0 });
  },

  endTour: () => {
    try {
      localStorage.setItem(TUTORIAL_COMPLETED_KEY, "true");
    } catch (err) {
      console.warn("Failed to persist tutorial flag to localStorage", err);
    }
    set({ tourActive: false });
  },

  advance: () => {
    set((state) => ({ tourStepIndex: state.tourStepIndex + 1 }));
  },
}));
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pnpm test --run src/stores/__tests__/tour-store.test.ts
```

Expected: PASS — all 4 tests.

- [ ] **Step 5: Run the full frontend suite to confirm no regression**

```bash
pnpm test --run
```

Expected: 142/142 (138 baseline + 4 new). Pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git add git-archiver-v2/src/stores/tour-store.ts git-archiver-v2/src/stores/__tests__/tour-store.test.ts
git commit -m "feat(tour-store): Zustand store + 4 tests for tour state

useTourStore tracks tourActive/tourStepIndex and exposes start/end/
advance actions. endTour persists 'git-archiver-tutorial-completed'
to localStorage; startTour clears it. Both wrap localStorage writes
in try/catch so quota or private-browsing failures don't crash the
tour."
```

---

## Task 2: OnboardingTour component

This is the wrapper around `<Joyride>`. It reads `tourActive` and `tourStepIndex` from the store, builds the steps array (conditionally dropping step 3 on empty repo list), and handles Joyride's callback to advance the index or end the tour. We don't write a vitest test for the component itself — Joyride's own behavior is covered upstream, and DOM-querying its internal portal from a test is brittle. Coverage of the integration is in Task 4 (App auto-start) and in manual smoke testing.

**Files:**
- Create: `git-archiver-v2/src/components/onboarding-tour.tsx`

- [ ] **Step 1: Create the component**

Create `git-archiver-v2/src/components/onboarding-tour.tsx`:

```tsx
import Joyride, { CallBackProps, STATUS, Step } from "react-joyride";
import { useTourStore } from "@/stores/tour-store";
import { useRepoStore } from "@/stores/repo-store";

/**
 * 4-step first-launch onboarding spotlight.
 *
 * Mounted once at the App root. Reads tour state from useTourStore. Steps
 * target elements via `data-tour-id` attributes the targeted components
 * expose. Step 3 (row actions) is dropped at tour-start time when there
 * are zero repos — Joyride needs a stable steps array for the duration
 * of the tour, so we build it once when tourActive flips to true.
 */
export function OnboardingTour() {
  const tourActive = useTourStore((s) => s.tourActive);
  const tourStepIndex = useTourStore((s) => s.tourStepIndex);
  const advance = useTourStore((s) => s.advance);
  const endTour = useTourStore((s) => s.endTour);

  // Read repos count once when tour starts; the steps array stays stable
  // for the duration of one tour run.
  const hasRepos = useRepoStore.getState().repos.length > 0;

  const steps: Step[] = [
    {
      target: "body",
      placement: "center",
      title: "Welcome to Git Archiver",
      content:
        "Track GitHub repositories and automatically snapshot them as compressed .tar.xz archives whenever they change. This quick tour takes 30 seconds.",
      disableBeacon: true,
    },
    {
      target: '[data-tour-id="add-repo-bar"]',
      placement: "bottom",
      title: "Add a repository",
      content:
        "Paste a GitHub URL (https://github.com/owner/repo) here and click Add. The app will clone the repo and create your first archive automatically.",
      disableBeacon: true,
    },
    ...(hasRepos
      ? [
          {
            target: '[data-tour-id="row-actions"]',
            placement: "left" as const,
            title: "Per-repo actions",
            content:
              "The ⋯ menu on each row lets you view archives, retry failed clones, copy the URL, or remove a repo. Status updates appear in the table as background tasks run.",
            disableBeacon: true,
          },
        ]
      : []),
    {
      target: '[data-tour-id="settings-button"]',
      placement: "bottom-end",
      title: "Settings",
      content:
        "Add a GitHub token (raises the API rate limit from 60 to 5,000/hour), schedule daily syncs, or change where clones are stored. You can replay this tour from here anytime.",
      disableBeacon: true,
    },
  ];

  const handleCallback = (data: CallBackProps) => {
    const { status, type } = data;
    if (
      status === STATUS.FINISHED ||
      status === STATUS.SKIPPED
    ) {
      endTour();
      return;
    }
    if (type === "step:after") {
      advance();
    }
  };

  return (
    <Joyride
      run={tourActive}
      stepIndex={tourStepIndex}
      steps={steps}
      callback={handleCallback}
      continuous
      showSkipButton
      disableScrolling={false}
      locale={{ last: "Got it" }}
      styles={{
        options: {
          // Use the Tailwind --primary CSS var so dark/light themes match.
          primaryColor: "hsl(var(--primary))",
          zIndex: 10000,
        },
      }}
    />
  );
}
```

- [ ] **Step 2: Confirm TypeScript compiles**

```bash
cd git-archiver-v2
pnpm tsc --noEmit
```

Expected: no errors. If react-joyride's TypeScript types complain about `placement: "left" as const` or about the `Step` union, the most likely fix is adjusting the cast — but the form above is correct for v2.9.x.

- [ ] **Step 3: Confirm the rest of the frontend tests still pass (nothing was touched, but verify)**

```bash
pnpm test --run
```

Expected: 142/142.

- [ ] **Step 4: Commit**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git add git-archiver-v2/src/components/onboarding-tour.tsx
git commit -m "feat(onboarding-tour): Joyride wrapper component

OnboardingTour reads tourActive/tourStepIndex from useTourStore, builds
a 4-step (or 3-step on empty repo list) steps array, and routes the
Joyride callback to either advance() or endTour() depending on
status/type. Uses the Tailwind --primary CSS variable so the spotlight
matches the active theme."
```

---

## Task 3: Add `data-tour-id` attributes to the three targeted components

Pure attribute additions — no test code needed (the attributes are validated by Task 4's integration test attempting to drive the tour through these targets).

**Files:**
- Modify: `git-archiver-v2/src/components/add-repo-bar.tsx`
- Modify: `git-archiver-v2/src/components/app-header.tsx`
- Modify: `git-archiver-v2/src/components/repo-table/row-actions.tsx`

- [ ] **Step 1: Tag AddRepoBar**

Open `git-archiver-v2/src/components/add-repo-bar.tsx`. The component returns a top-level wrapper element (likely a `div` with classnames like `flex gap-2` or similar). Add `data-tour-id="add-repo-bar"` as a prop on that outer element.

Example — if the outer element looks like:

```tsx
<div className="flex items-center gap-2">
```

change it to:

```tsx
<div className="flex items-center gap-2" data-tour-id="add-repo-bar">
```

If the outer element is a different shape (e.g. a fragment), wrap it in a `<div data-tour-id="add-repo-bar" className="contents">` so Joyride has a real DOM node to spotlight.

- [ ] **Step 2: Tag the Settings cog in AppHeader**

Open `git-archiver-v2/src/components/app-header.tsx`. Find the Settings button (it'll be a Button or IconButton around a `Settings` or cog icon from lucide-react, and its onClick opens the SettingsDialog). Add `data-tour-id="settings-button"` to that Button.

Example — if the button looks like:

```tsx
<Button variant="ghost" size="icon" onClick={() => setSettingsOpen(true)} aria-label="Settings">
  <Settings className="h-4 w-4" />
</Button>
```

change to:

```tsx
<Button
  variant="ghost"
  size="icon"
  onClick={() => setSettingsOpen(true)}
  aria-label="Settings"
  data-tour-id="settings-button"
>
  <Settings className="h-4 w-4" />
</Button>
```

- [ ] **Step 3: Tag the row-actions trigger**

Open `git-archiver-v2/src/components/repo-table/row-actions.tsx`. Find the `<DropdownMenuTrigger asChild>` block wrapping the MoreHorizontal Button (around line 108-117 in the current file). Add `data-tour-id="row-actions"` on the Button itself.

The current code:

```tsx
<DropdownMenuTrigger asChild>
  <Button
    variant="ghost"
    size="icon"
    className="h-8 w-8"
    aria-label="Row actions"
  >
    <MoreHorizontal className="h-4 w-4" />
  </Button>
</DropdownMenuTrigger>
```

becomes:

```tsx
<DropdownMenuTrigger asChild>
  <Button
    variant="ghost"
    size="icon"
    className="h-8 w-8"
    aria-label="Row actions"
    data-tour-id="row-actions"
  >
    <MoreHorizontal className="h-4 w-4" />
  </Button>
</DropdownMenuTrigger>
```

Joyride picks the first DOM match of the selector, so we don't need to disambiguate across multiple rows.

- [ ] **Step 4: Run tests to confirm no regressions**

```bash
cd git-archiver-v2
pnpm test --run
```

Expected: 142/142 (the existing data-table and add-repo-bar tests still pass — `data-*` attributes don't interfere with React Testing Library queries).

- [ ] **Step 5: Commit**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git add git-archiver-v2/src/components/add-repo-bar.tsx git-archiver-v2/src/components/app-header.tsx git-archiver-v2/src/components/repo-table/row-actions.tsx
git commit -m "feat(tour-targets): add data-tour-id to AddRepoBar, settings cog, row-actions

Three stable selectors for OnboardingTour to spotlight. No behavior
change — pure attribute additions."
```

---

## Task 4: Mount OnboardingTour + auto-start logic + 2 tests

The integration step. The `<OnboardingTour />` component goes into `App.tsx` next to `<Toaster />`. The existing mount-time `useEffect` (currently calls `repoStore.fetchRepos()` and `settingsStore.fetchSettings()`) gets a third line that conditionally fires `useTourStore.getState().startTour()`. Two tests in `app.test.tsx` validate the auto-start behavior.

**Files:**
- Modify: `git-archiver-v2/src/App.tsx`
- Modify: `git-archiver-v2/src/__tests__/app.test.tsx`

- [ ] **Step 1: Write the two failing tests**

Open `git-archiver-v2/src/__tests__/app.test.tsx`. Add the following two tests inside the existing `describe("App", ...)` block (or in a new `describe("App tutorial auto-start", ...)` block — both work):

```ts
import { useTourStore, TUTORIAL_COMPLETED_KEY } from "@/stores/tour-store";

// (existing tests stay above this)

describe("App tutorial auto-start", () => {
  beforeEach(() => {
    useTourStore.setState({ tourActive: false, tourStepIndex: 0 });
    localStorage.clear();
  });

  it("starts the tour on mount when the completion flag is unset", async () => {
    render(<App />);
    await waitFor(() => {
      expect(useTourStore.getState().tourActive).toBe(true);
    });
  });

  it("does not start the tour when the completion flag is set", async () => {
    localStorage.setItem(TUTORIAL_COMPLETED_KEY, "true");
    render(<App />);
    // Give effects a tick to run
    await new Promise((r) => setTimeout(r, 50));
    expect(useTourStore.getState().tourActive).toBe(false);
  });
});
```

You'll also need to mock `react-joyride` so the test environment doesn't try to render the portal. Add this mock near the existing mocks at the top of the file:

```ts
vi.mock("react-joyride", () => ({
  default: () => null,
  STATUS: { FINISHED: "finished", SKIPPED: "skipped" },
}));
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd git-archiver-v2
pnpm test --run src/__tests__/app.test.tsx
```

Expected: the two new tests FAIL. The first fails because App doesn't call `startTour()`. The second passes vacuously (tourActive defaults to false) but that's OK — we still want both there to lock in behavior in both directions.

- [ ] **Step 3: Wire OnboardingTour and auto-start logic into App**

Open `git-archiver-v2/src/App.tsx`. Add the import alongside other component imports:

```tsx
import { OnboardingTour } from "@/components/onboarding-tour";
import { useTourStore, TUTORIAL_COMPLETED_KEY } from "@/stores/tour-store";
```

Modify the existing mount-time effect (currently around lines 37-41):

```tsx
// Initial data fetch on mount
useEffect(() => {
  repoStore.fetchRepos();
  settingsStore.fetchSettings();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

to:

```tsx
// Initial data fetch on mount
useEffect(() => {
  repoStore.fetchRepos();
  settingsStore.fetchSettings();
  // First-launch onboarding tour. Reuse useTourStore.getState() to read
  // live state and dispatch synchronously without taking a dep on the store.
  if (localStorage.getItem(TUTORIAL_COMPLETED_KEY) !== "true") {
    useTourStore.getState().startTour();
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

Mount the OnboardingTour in the returned JSX, alongside `<Toaster />`:

```tsx
return (
  <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
    <div className="flex flex-col h-screen bg-background text-foreground">
      <AppHeader />
      <main className="flex-1 overflow-auto p-4 space-y-4">
        <AddRepoBar />
        <DataTable />
      </main>
      <ActivityLog />
      <StatusBar />
    </div>
    <OnboardingTour />
    <Toaster />
  </ThemeProvider>
);
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
pnpm test --run src/__tests__/app.test.tsx
```

Expected: PASS — both new tests + all existing app tests still pass.

- [ ] **Step 5: Run the full frontend suite**

```bash
pnpm test --run
```

Expected: 144/144 (142 + 2 new). Pass.

- [ ] **Step 6: Type-check**

```bash
pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git add git-archiver-v2/src/App.tsx git-archiver-v2/src/__tests__/app.test.tsx
git commit -m "feat(app): mount OnboardingTour + auto-start on first launch

App.tsx mounts <OnboardingTour /> alongside <Toaster />. The existing
mount-time useEffect now checks localStorage.git-archiver-tutorial-
completed and calls useTourStore.getState().startTour() when unset.
Two new tests in app.test.tsx lock in both directions of the
conditional."
```

---

## Task 5: Settings dialog "Help" section with "Show tutorial again" button

The replay path. Add a new section at the bottom of the SettingsDialog (after the existing fields, before the dialog footer) labeled "Help" with one button that closes the dialog and then re-starts the tour after a 200ms delay so the Radix close animation doesn't fight the spotlight portal.

**Files:**
- Modify: `git-archiver-v2/src/components/dialogs/settings-dialog.tsx`

- [ ] **Step 1: Add the import**

Open `git-archiver-v2/src/components/dialogs/settings-dialog.tsx`. Add the tour store import alongside the other store/util imports:

```tsx
import { useTourStore } from "@/stores/tour-store";
```

- [ ] **Step 2: Add the handler**

Find the existing handler functions (`handleTestToken`, `handleSave`). After them, add:

```tsx
const handleReplayTour = () => {
  onOpenChange(false);
  // Wait for the Radix DialogContent close animation (~150ms) before
  // starting the tour, so the spotlight portal doesn't render over a
  // half-closed dialog.
  setTimeout(() => {
    useTourStore.getState().startTour();
  }, 200);
};
```

- [ ] **Step 3: Add the Help section to the JSX**

Find the end of the existing form sections (just before the `<DialogFooter>`). Insert a new "Help" section. The exact JSX depends on the existing pattern in this file — match the typography and spacing of nearby sections. A reasonable addition:

```tsx
<div className="space-y-2 pt-2 border-t">
  <h4 className="text-sm font-medium">Help</h4>
  <Button
    variant="outline"
    size="sm"
    onClick={handleReplayTour}
  >
    Show tutorial again
  </Button>
  <p className="text-xs text-muted-foreground">
    Replays the first-launch walkthrough.
  </p>
</div>
```

If `Button` isn't already imported in the file, the existing imports at the top of the file should already include it (the existing settings dialog uses Buttons for Save/Cancel). If not, add `import { Button } from "@/components/ui/button";`.

- [ ] **Step 4: Run frontend tests to verify no regressions**

```bash
cd git-archiver-v2
pnpm test --run
```

Expected: 144/144 still pass. The existing `settings-dialog.test.tsx` doesn't assert anything about the Help section, so it won't break.

- [ ] **Step 5: Type-check**

```bash
pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git add git-archiver-v2/src/components/dialogs/settings-dialog.tsx
git commit -m "feat(settings-dialog): Help section with 'Show tutorial again' button

Adds a Help section at the bottom of the settings dialog with a single
Outline button that closes the dialog, waits 200ms for the Radix close
animation, then calls useTourStore.getState().startTour() to replay
the onboarding walkthrough."
```

---

## Wrap-up

### Wrap-1: Final verification + manual smoke

- [ ] **Step 1: Full test + lint pass**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver/git-archiver-v2
cargo test --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
pnpm test --run
pnpm tsc --noEmit
```

Expected: all green. The Rust side has not been touched by this work, so the Rust commands should pass identically to baseline.

- [ ] **Step 2: Manual smoke — first launch path**

```bash
# Wipe the localStorage flag (and confirm a clean app state)
# In macOS the WebView's localStorage lives inside the app's data dir.
# Easiest reset: open DevTools in the running app (Cmd+Option+I) and run:
#   localStorage.removeItem("git-archiver-tutorial-completed")
# Then close and re-open the app, OR refresh the dev window.

cd git-archiver-v2
pnpm tauri dev
```

In the launched app, verify:
1. The Welcome step appears, centered, with dimmed background.
2. Clicking "Next" advances to the AddRepoBar spotlight.
3. (If you have 0 repos) "Next" goes directly to the Settings cog (skipping the row-actions step). Otherwise the row-actions step appears between.
4. The final step's button label is "Got it" (not "Last").
5. Clicking "Got it" dismisses the tour.
6. Closing and re-opening the app does NOT replay the tour.

- [ ] **Step 3: Manual smoke — replay path**

In the same running app (or after restart):
1. Click the Settings cog.
2. Scroll to the bottom of the dialog. The "Help" section is visible with a "Show tutorial again" button.
3. Click "Show tutorial again". The dialog closes, briefly pauses, then the tour starts from the Welcome step.
4. Skip or complete the tour; verify localStorage `git-archiver-tutorial-completed` is set back to `"true"`.

- [ ] **Step 4: Manual smoke — theme switch**

Mid-tour (between any two steps), toggle the theme via the existing theme button. The tooltip background/text colors should follow the theme change.

- [ ] **Step 5: Push**

```bash
cd /Users/jacobkanfer/CodeRepos/Git-Archiver
git log --oneline main..HEAD  # OR: git log --oneline -10 if working directly on main
git push origin main
```

Watch the next CI run; expect it to pass cleanly. No new dependencies were added on the Rust side and the cargo audit + cargo clippy paths are untouched.

---

## Plan Self-Review

**Spec coverage:**
- Architecture (Zustand store + single `<Joyride>` at App root): Task 1, 2, 4 ✓
- 4-step content (welcome / add / row-actions / settings): Task 2 ✓
- Conditional drop of step 3 on empty repo list: Task 2 (steps array spread) ✓
- localStorage flag (`git-archiver-tutorial-completed`): Task 1 (constant + read/write) ✓
- App auto-start on flag-unset: Task 4 ✓
- Settings Help section + replay button: Task 5 ✓
- 200ms post-close delay: Task 5 (handleReplayTour) ✓
- `data-tour-id` selectors on AddRepoBar / settings cog / row-actions: Task 3 ✓
- react-joyride dependency: Setup-1 ✓
- All 6 listed tests in the spec testing table: Task 1 (4 store tests) + Task 4 (2 app tests) ✓
- Joyride config (`continuous`, `showSkipButton`, primary color from CSS var, "Got it" locale): Task 2 ✓
- localStorage failure handling: Task 1 (try/catch in store) + tested ✓

**Placeholder scan:** No "TBD", "implement later", or vague "handle edge cases" steps. Every code step has complete code. The Step 1 in Task 3 has a fallback ("if the outer element is a different shape ...") which is intentional adaptation guidance, not a placeholder.

**Type consistency:** `TUTORIAL_COMPLETED_KEY` exported from `tour-store.ts` is imported by both `App.tsx` (Task 4) and the test files (Task 1, Task 4). `useTourStore.getState().startTour()` / `.endTour()` / `.advance()` method names appear consistently across Task 1, 2, 4, 5. `data-tour-id="add-repo-bar"` / `="row-actions"` / `="settings-button"` match between Task 2's selectors and Task 3's attribute additions. ✓
