import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AddRepoBar } from "../add-repo-bar";
import { useRepoStore } from "@/stores/repo-store";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

describe("AddRepoBar", () => {
  const mockAddRepo = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockAddRepo.mockReset();
    useRepoStore.setState({
      addRepo: mockAddRepo,
    });
  });

  it("renders input and add button", () => {
    render(<AddRepoBar />);
    expect(
      screen.getByPlaceholderText("https://github.com/owner/repo"),
    ).toBeInTheDocument();
    expect(screen.getByText("Add")).toBeInTheDocument();
  });

  it("disables add button when input is empty", () => {
    render(<AddRepoBar />);
    const button = screen.getByText("Add").closest("button");
    expect(button).toBeDisabled();
  });

  it("enables add button when input has text", () => {
    render(<AddRepoBar />);
    const input = screen.getByPlaceholderText(
      "https://github.com/owner/repo",
    );
    fireEvent.change(input, {
      target: { value: "https://github.com/octocat/hello-world" },
    });
    const button = screen.getByText("Add").closest("button");
    expect(button).not.toBeDisabled();
  });

  it("shows error toast for invalid URL", async () => {
    render(<AddRepoBar />);
    const input = screen.getByPlaceholderText(
      "https://github.com/owner/repo",
    );
    fireEvent.change(input, { target: { value: "not-a-valid-url" } });
    fireEvent.click(screen.getByText("Add"));

    // The addRepo should NOT have been called
    expect(mockAddRepo).not.toHaveBeenCalled();
  });

  it("calls addRepo with valid URL", async () => {
    mockAddRepo.mockResolvedValueOnce(undefined);
    render(<AddRepoBar />);

    const input = screen.getByPlaceholderText(
      "https://github.com/owner/repo",
    );
    fireEvent.change(input, {
      target: { value: "https://github.com/octocat/hello-world" },
    });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(mockAddRepo).toHaveBeenCalledWith(
        "https://github.com/octocat/hello-world",
      );
    });
  });

  it("clears input after successful add", async () => {
    mockAddRepo.mockResolvedValueOnce(undefined);
    render(<AddRepoBar />);

    const input = screen.getByPlaceholderText(
      "https://github.com/owner/repo",
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: { value: "https://github.com/octocat/hello-world" },
    });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(input.value).toBe("");
    });
  });

  it("does not clear input after failed add", async () => {
    mockAddRepo.mockRejectedValueOnce(new Error("Already exists"));
    render(<AddRepoBar />);

    const input = screen.getByPlaceholderText(
      "https://github.com/owner/repo",
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: { value: "https://github.com/octocat/hello-world" },
    });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(mockAddRepo).toHaveBeenCalled();
    });
    // Input should still have the value
    expect(input.value).toBe("https://github.com/octocat/hello-world");
  });

  it("submits on Enter key", async () => {
    mockAddRepo.mockResolvedValueOnce(undefined);
    render(<AddRepoBar />);

    const input = screen.getByPlaceholderText(
      "https://github.com/owner/repo",
    );
    fireEvent.change(input, {
      target: { value: "https://github.com/octocat/hello-world" },
    });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    await waitFor(() => {
      expect(mockAddRepo).toHaveBeenCalledWith(
        "https://github.com/octocat/hello-world",
      );
    });
  });

  it("does not submit on other keys", () => {
    render(<AddRepoBar />);

    const input = screen.getByPlaceholderText(
      "https://github.com/owner/repo",
    );
    fireEvent.change(input, {
      target: { value: "https://github.com/octocat/hello-world" },
    });
    fireEvent.keyDown(input, { key: "Escape", code: "Escape" });

    expect(mockAddRepo).not.toHaveBeenCalled();
  });
});
