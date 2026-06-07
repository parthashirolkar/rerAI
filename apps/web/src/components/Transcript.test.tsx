import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { Transcript } from "./Transcript";

const samples = [
  "Assess permit feasibility for Survey No. 45/2, Baner.",
  "Check setbacks near Hinjewadi Phase 2.",
];

describe("Transcript", () => {
  test("renders sample queries and emits the selected query", () => {
    const onUseSample = vi.fn();

    render(
      <Transcript
        hasMessages={false}
        isStreaming={false}
        showThinking={false}
        messages={[]}
        sampleQueries={samples}
        onUseSample={onUseSample}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: samples[0] }));

    expect(screen.getByText("How can I help?")).toBeInTheDocument();
    expect(onUseSample).toHaveBeenCalledWith(samples[0]);
  });

  test("renders user and assistant messages", () => {
    render(
      <Transcript
        hasMessages
        isStreaming={false}
        showThinking={false}
        messages={[
          { role: "user", content: "Check this site", createdAt: 1 },
          { role: "assistant", content: "The site needs setback review.", createdAt: 2 },
        ]}
        sampleQueries={samples}
        onUseSample={vi.fn()}
      />,
    );

    expect(screen.getByText("Check this site")).toBeInTheDocument();
    expect(screen.getByText("The site needs setback review.")).toBeInTheDocument();
    expect(screen.queryByText("How can I help?")).not.toBeInTheDocument();
  });

  test("renders complete turns by explicit position with one Assistant Response", () => {
    const { container } = render(
      <Transcript
        hasMessages
        isStreaming={false}
        showThinking={false}
        messages={[]}
        turns={[
          {
            turnId: "turn-2",
            turnPosition: 1,
            userContent: "Second question",
            status: "completed",
            createdAt: 100,
            assistantMessages: [
              {
                id: "ai-2a",
                messagePosition: 0,
                canonicalContent: "Second progress",
                createdAt: 101,
              },
              {
                id: "ai-2b",
                messagePosition: 1,
                canonicalContent: "Second answer",
                createdAt: 102,
              },
            ],
          },
          {
            turnId: "turn-1",
            turnPosition: 0,
            userContent: "First question",
            status: "completed",
            createdAt: 300,
            assistantMessages: [
              {
                id: "ai-1",
                messagePosition: 0,
                canonicalContent: "First answer",
                createdAt: 400,
              },
            ],
          },
        ]}
        sampleQueries={samples}
        onUseSample={vi.fn()}
      />,
    );

    const text = container.textContent ?? "";
    expect(text.indexOf("First question")).toBeLessThan(text.indexOf("First answer"));
    expect(text.indexOf("First answer")).toBeLessThan(text.indexOf("Second question"));
    expect(text.indexOf("Second progress")).toBeLessThan(text.indexOf("Second answer"));
    expect(screen.getAllByTestId("assistant-response")).toHaveLength(2);
  });

  test("shows thinking indicator only when requested", () => {
    const { container, rerender } = render(
      <Transcript
        hasMessages
        isStreaming={false}
        showThinking
        messages={[{ role: "user", content: "Check this site", createdAt: 1 }]}
        sampleQueries={samples}
        onUseSample={vi.fn()}
      />,
    );

    expect(container.querySelectorAll(".typing-dot")).toHaveLength(3);

    rerender(
      <Transcript
        hasMessages
        isStreaming={false}
        showThinking={false}
        messages={[{ role: "user", content: "Check this site", createdAt: 1 }]}
        sampleQueries={samples}
        onUseSample={vi.fn()}
      />,
    );

    expect(container.querySelectorAll(".typing-dot")).toHaveLength(0);
  });
});
