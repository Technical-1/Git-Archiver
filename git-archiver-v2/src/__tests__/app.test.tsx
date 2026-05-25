import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../App";
import { useTourStore, TUTORIAL_COMPLETED_KEY } from "@/stores/tour-store";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue([]),
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn().mockResolvedValue(() => {}),
}));

vi.mock("react-joyride", () => ({
  Joyride: () => null,
  STATUS: { FINISHED: "finished", SKIPPED: "skipped" },
  EVENTS: { STEP_AFTER: "step:after" },
}));

describe("App", () => {
  it("renders the app title", async () => {
    render(<App />);
    expect(screen.getByText("Git Archiver")).toBeInTheDocument();
    // Wait for async effects to settle
    await waitFor(() => {
      expect(screen.getAllByText("0 repositories").length).toBeGreaterThan(0);
    });
  });

  it("renders activity log", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("activity-log")).toBeInTheDocument();
    });
  });

  it("renders status bar", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("status-bar")).toBeInTheDocument();
    });
  });

  it("subscribes to tauri events on mount", async () => {
    const { listen } = await import("@tauri-apps/api/event");
    render(<App />);
    await waitFor(() => {
      expect(listen).toHaveBeenCalledWith(
        "task-progress",
        expect.any(Function),
      );
      expect(listen).toHaveBeenCalledWith(
        "repo-updated",
        expect.any(Function),
      );
    });
  });
});

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
