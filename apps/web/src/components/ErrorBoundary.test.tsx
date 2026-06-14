import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Thrower() {
  throw new Error("Render failed");
}

describe("ErrorBoundary", () => {
  test("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <div>healthy</div>
      </ErrorBoundary>,
    );

    expect(screen.getByText("healthy")).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  test("renders recovery UI and resets when a child throws", () => {
    const onReset = vi.fn();
    const originalError = console.error;
    console.error = vi.fn();

    try {
      render(
        <ErrorBoundary onReset={onReset}>
          <Thrower />
        </ErrorBoundary>,
      );
    } finally {
      console.error = originalError;
    }

    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByText("Render failed")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /start blank chat/i }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
