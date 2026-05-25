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
