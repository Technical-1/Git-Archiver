import { Joyride, STATUS, Step, EventData, EVENTS } from "react-joyride";
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
      skipBeacon: true,
    },
    {
      target: '[data-tour-id="add-repo-bar"]',
      placement: "bottom",
      title: "Add a repository",
      content:
        "Paste a GitHub URL (https://github.com/owner/repo) here and click Add. The app will clone the repo and create your first archive automatically.",
      skipBeacon: true,
    },
    ...(hasRepos
      ? [
          {
            target: '[data-tour-id="row-actions"]',
            placement: "left" as const,
            title: "Per-repo actions",
            content:
              "The ⋯ menu on each row lets you view archives, retry failed clones, copy the URL, or remove a repo. Status updates appear in the table as background tasks run.",
            skipBeacon: true,
          },
        ]
      : []),
    {
      target: '[data-tour-id="settings-button"]',
      placement: "bottom-end",
      title: "Settings",
      content:
        "Add a GitHub token (raises the API rate limit from 60 to 5,000/hour), schedule daily syncs, or change where clones are stored. You can replay this tour from here anytime.",
      skipBeacon: true,
    },
  ];

  const handleEvent = (data: EventData) => {
    const { type, status } = data;
    if (
      status === STATUS.FINISHED ||
      status === STATUS.SKIPPED
    ) {
      endTour();
      return;
    }
    if (type === EVENTS.STEP_AFTER) {
      advance();
    }
  };

  return (
    <Joyride
      run={tourActive}
      stepIndex={tourStepIndex}
      steps={steps}
      onEvent={handleEvent}
      continuous
      locale={{ last: "Got it" }}
      options={{
        // Use the Tailwind --primary CSS var so dark/light themes match.
        primaryColor: "hsl(var(--primary))",
        zIndex: 10000,
        // v3 default buttons are ['back', 'close', 'primary'] — explicitly include
        // 'skip' so the user can dismiss the tour at any step. Drop 'back' since
        // our tour is short and forward-only.
        buttons: ["skip", "primary"],
      }}
    />
  );
}
