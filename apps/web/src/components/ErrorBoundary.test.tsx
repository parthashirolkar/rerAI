import { Window } from "happy-dom";

const window = new Window();
(globalThis as unknown as Record<string, unknown>).document = window.document;
(globalThis as unknown as Record<string, unknown>).window = window;

import { describe, expect, test } from "bun:test";
import { Component, type ReactNode, createElement } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";

// Lightweight inline error boundary for testing the pattern without
// requiring path-alias resolution for UI components.
type TestBoundaryProps = { children: ReactNode };
type TestBoundaryState = { hasError: boolean; message: string };

class TestBoundary extends Component<TestBoundaryProps, TestBoundaryState> {
  constructor(props: TestBoundaryProps) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): TestBoundaryState {
    return { hasError: true, message: error.message };
  }

  render() {
    if (this.state.hasError) {
      return createElement("div", { "data-testid": "recovery" }, [
        createElement("span", { key: "title" }, "Something went wrong"),
        createElement("button", { key: "action" }, "Start blank chat"),
        createElement("code", { key: "msg" }, this.state.message),
      ]);
    }
    return this.props.children;
  }
}

function Thrower({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error("Test error");
  }
  return createElement("div", null, "healthy");
}

describe("ErrorBoundary pattern", () => {
  test("renders children when there is no error", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    flushSync(() => {
      root.render(
        createElement(TestBoundary, null, createElement(Thrower, { shouldThrow: false }))
      );
    });
    expect(container.innerHTML).toContain("healthy");
    expect(container.innerHTML).not.toContain("Something went wrong");
    root.unmount();
    document.body.removeChild(container);
  });

  test("renders recovery UI when a child throws instead of blanking the page", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const originalError = console.error;
    console.error = () => {};
    try {
      flushSync(() => {
        root.render(
          createElement(TestBoundary, null, createElement(Thrower, { shouldThrow: true }))
        );
      });
    } catch {
      // React may re-throw during flushSync even though the boundary catches it.
    } finally {
      console.error = originalError;
    }
    expect(container.innerHTML).toContain("Something went wrong");
    expect(container.innerHTML).toContain("Start blank chat");
    expect(container.innerHTML).toContain("Test error");
    expect(container.innerHTML).not.toContain("healthy");
    root.unmount();
    document.body.removeChild(container);
  });
});
