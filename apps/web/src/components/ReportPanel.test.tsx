import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { ReportPanel } from "./ReportPanel";

describe("ReportPanel", () => {
  test("renders report summary and sections", () => {
    render(
      <ReportPanel
        error={null}
        report={{
          summary: "Feasibility is conditional.",
          sections: [
            { title: "Plot Identification", body: "Survey No. 45/2 in Baner." },
            { title: "Recommendations", body: "Verify setbacks." },
          ],
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Report" })).toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Feasibility is conditional.")).toBeInTheDocument();
    expect(screen.getByText("Plot Identification")).toBeInTheDocument();
    expect(screen.getByText("Survey No. 45/2 in Baner.")).toBeInTheDocument();
    expect(screen.getByText("Recommendations")).toBeInTheDocument();
  });

  test("renders stream errors and an empty report state", () => {
    render(
      <ReportPanel
        error={new Error("Stream disconnected")}
        report={{ summary: "", sections: [] }}
      />,
    );

    expect(screen.getByText("Connection error")).toBeInTheDocument();
    expect(screen.getByText("Stream disconnected")).toBeInTheDocument();
    expect(screen.getByText("Report sections will appear here after analysis")).toBeInTheDocument();
  });
});
