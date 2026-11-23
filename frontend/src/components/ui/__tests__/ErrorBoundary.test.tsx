import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ErrorBoundary } from "../ErrorBoundary";

const CrashingChild = ({ shouldCrash }: { shouldCrash: boolean }) => {
  if (shouldCrash) {
    throw new Error("Simulated rendering explosion");
  }
  return <div>Safe child content</div>;
};

describe("ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("renders children normally when no error occurs", () => {
    render(
      <ErrorBoundary>
        <CrashingChild shouldCrash={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Safe child content")).toBeDefined();
    expect(screen.queryByText("Something went wrong")).toBeNull();
  });

  it("catches render error and renders default recovery UI with error message and actions", () => {
    render(
      <ErrorBoundary>
        <CrashingChild shouldCrash={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Something went wrong")).toBeDefined();
    expect(screen.getByText(/Simulated rendering explosion/)).toBeDefined();
    expect(screen.getByText("Reload Page")).toBeDefined();
    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.queryByText("Safe child content")).toBeNull();
  });

  it("renders custom fallback prop when provided", () => {
    render(
      <ErrorBoundary fallback={<div>Custom recovery card</div>}>
        <CrashingChild shouldCrash={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Custom recovery card")).toBeDefined();
    expect(screen.queryByText("Something went wrong")).toBeNull();
  });
});
