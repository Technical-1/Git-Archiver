import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import App from "../App";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue([]),
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn().mockResolvedValue(() => {}),
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
