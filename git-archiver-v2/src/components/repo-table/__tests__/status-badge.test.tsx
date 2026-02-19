import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusBadge } from "../status-badge";
import type { RepoStatus } from "@/lib/types";

describe("StatusBadge", () => {
  const statuses: { status: RepoStatus; label: string }[] = [
    { status: "active", label: "Active" },
    { status: "pending", label: "Pending" },
    { status: "archived", label: "Archived" },
    { status: "deleted", label: "Deleted" },
    { status: "error", label: "Error" },
  ];

  statuses.forEach(({ status, label }) => {
    it(`renders "${label}" for status "${status}"`, () => {
      render(<StatusBadge status={status} />);
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });
});
