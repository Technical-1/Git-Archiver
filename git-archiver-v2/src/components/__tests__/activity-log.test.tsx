import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { ActivityLog } from "../activity-log";
import { useTaskStore } from "@/stores/task-store";

describe("ActivityLog", () => {
  beforeEach(() => {
    useTaskStore.setState({ activityLog: [] });
  });

  it("renders collapsed by default with entry count", () => {
    render(<ActivityLog />);
    expect(screen.getByText("Activity Log (0)")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-log-entries")).not.toBeInTheDocument();
  });

  it("expands when toggle button is clicked", () => {
    render(<ActivityLog />);
    fireEvent.click(screen.getByText("Activity Log (0)"));
    expect(screen.getByTestId("activity-log-entries")).toBeInTheDocument();
    expect(screen.getByText("No activity yet.")).toBeInTheDocument();
  });

  it("collapses when toggle button is clicked again", () => {
    render(<ActivityLog />);
    fireEvent.click(screen.getByText("Activity Log (0)"));
    expect(screen.getByTestId("activity-log-entries")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Activity Log (0)"));
    expect(screen.queryByTestId("activity-log-entries")).not.toBeInTheDocument();
  });

  it("displays activity entries when expanded", () => {
    useTaskStore.setState({
      activityLog: [
        {
          id: "1",
          timestamp: "2026-01-15T10:30:00Z",
          message: "Cloned repo successfully",
          type: "success",
        },
        {
          id: "2",
          timestamp: "2026-01-15T10:31:00Z",
          message: "Failed to update repo",
          type: "error",
        },
      ],
    });

    render(<ActivityLog />);
    expect(screen.getByText("Activity Log (2)")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Activity Log (2)"));
    expect(screen.getByText("Cloned repo successfully")).toBeInTheDocument();
    expect(screen.getByText("Failed to update repo")).toBeInTheDocument();
  });

  it("shows all four entry types with correct messages", () => {
    useTaskStore.setState({
      activityLog: [
        {
          id: "1",
          timestamp: "2026-01-15T10:30:00Z",
          message: "Success message",
          type: "success",
        },
        {
          id: "2",
          timestamp: "2026-01-15T10:31:00Z",
          message: "Error message",
          type: "error",
        },
        {
          id: "3",
          timestamp: "2026-01-15T10:32:00Z",
          message: "Info message",
          type: "info",
        },
        {
          id: "4",
          timestamp: "2026-01-15T10:33:00Z",
          message: "Warning message",
          type: "warning",
        },
      ],
    });

    render(<ActivityLog />);
    fireEvent.click(screen.getByText("Activity Log (4)"));

    expect(screen.getByText("Success message")).toBeInTheDocument();
    expect(screen.getByText("Error message")).toBeInTheDocument();
    expect(screen.getByText("Info message")).toBeInTheDocument();
    expect(screen.getByText("Warning message")).toBeInTheDocument();
  });
});
