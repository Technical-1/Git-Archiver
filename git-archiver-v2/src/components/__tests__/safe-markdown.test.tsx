import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SafeMarkdown } from "../safe-markdown";

vi.mock("@tauri-apps/plugin-opener", () => ({
  openUrl: vi.fn().mockResolvedValue(undefined),
}));

describe("SafeMarkdown", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders an http link as an anchor and routes clicks through openUrl", async () => {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    render(<SafeMarkdown>{"[click](https://example.com)"}</SafeMarkdown>);
    const a = screen.getByText("click");
    expect(a.closest("a")).not.toBeNull();
    fireEvent.click(a);
    expect(openUrl).toHaveBeenCalledWith("https://example.com");
  });

  it("renders an https link the same way", async () => {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    render(<SafeMarkdown>{"[secure](https://example.org/path?q=1)"}</SafeMarkdown>);
    fireEvent.click(screen.getByText("secure"));
    expect(openUrl).toHaveBeenCalledWith("https://example.org/path?q=1");
  });

  it("does not render a javascript: link as a clickable anchor", () => {
    render(<SafeMarkdown>{"[evil](javascript:alert(1))"}</SafeMarkdown>);
    const evil = screen.getByText("evil");
    expect(evil.closest("a")).toBeNull();
  });

  it("does not render a data: link as an anchor", () => {
    render(<SafeMarkdown>{"[evil](data:text/html,<script>alert(1)</script>)"}</SafeMarkdown>);
    expect(screen.getByText("evil").closest("a")).toBeNull();
  });

  it("does not render a file: link as an anchor", () => {
    render(<SafeMarkdown>{"[evil](file:///etc/passwd)"}</SafeMarkdown>);
    expect(screen.getByText("evil").closest("a")).toBeNull();
  });

  it("renders regular markdown text without scheme filtering interfering", () => {
    render(<SafeMarkdown>{"# Heading\n\nSome **bold** text."}</SafeMarkdown>);
    expect(screen.getByText("Heading")).toBeInTheDocument();
    expect(screen.getByText("bold")).toBeInTheDocument();
  });
});
