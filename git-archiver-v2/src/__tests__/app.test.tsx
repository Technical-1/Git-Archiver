import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import App from "../App";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue([]),
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
});
