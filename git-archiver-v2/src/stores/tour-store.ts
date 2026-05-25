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
