export type ReportSection = {
  title: string;
  body: string;
};

export type ParsedPermitReport = {
  summary: string;
  sections: ReportSection[];
};

export type ProgressState = {
  label: string;
  detail: string;
};

const SECTION_TITLES = [
  "Plot Identification",
  "Title & Ownership",
  "Spatial Context",
  "Regulatory Assessment",
  "RERA Compliance",
  "Summary & Recommendations",
  "Recommendations",
  "Assumptions",
  "Key Constraints",
];

export function parsePermitReport(markdown: string): ParsedPermitReport {
  if (!markdown.trim()) {
    return { summary: "", sections: [] };
  }

  const normalized = markdown.replace(/\r\n/g, "\n");
  const headingRegex = /^#{1,3}\s+(.+)$/gm;
  const matches = Array.from(normalized.matchAll(headingRegex));

  if (!matches.length) {
    return {
      summary: normalized.trim(),
      sections: [],
    };
  }

  const sections: ReportSection[] = [];
  let summary = normalized.slice(0, matches[0]?.index ?? 0).trim();

  for (let index = 0; index < matches.length; index += 1) {
    const current = matches[index];
    const next = matches[index + 1];
    const rawTitle = current[1]?.trim() ?? "";
    const start = (current.index ?? 0) + current[0].length;
    const end = next?.index ?? normalized.length;
    const body = normalized.slice(start, end).trim();

    if (!body) {
      continue;
    }

    const normalizedTitle = normalizeTitle(rawTitle);
    if (normalizedTitle.toLowerCase() === "permit feasibility report") {
      if (!summary) {
        summary = body;
      }
      continue;
    }

    sections.push({
      title: normalizedTitle,
      body,
    });
  }

  const prioritizedSections = sections.sort((left, right) => {
    return getTitleRank(left.title) - getTitleRank(right.title);
  });

  return {
    summary,
    sections: prioritizedSections,
  };
}

function normalizeTitle(title: string) {
  return title
    .replace(/^\d+(\.\d+)*\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function getTitleRank(title: string) {
  const exactIndex = SECTION_TITLES.findIndex((candidate) => candidate.toLowerCase() === title.toLowerCase());
  if (exactIndex >= 0) {
    return exactIndex;
  }

  const partialIndex = SECTION_TITLES.findIndex((candidate) =>
    title.toLowerCase().includes(candidate.toLowerCase()) ||
    candidate.toLowerCase().includes(title.toLowerCase()),
  );

  return partialIndex >= 0 ? partialIndex : SECTION_TITLES.length + 1;
}

export function deriveProgressState(
  isLoading: boolean,
  lastSubmittedAt: number | null,
  activeRunId: string | null,
): ProgressState {
  if (!isLoading) {
    if (activeRunId) {
      return {
        label: "Disconnected",
        detail: "Reconnecting to the active run.",
      };
    }

    return {
      label: "Ready",
      detail: "Send a message to start.",
    };
  }

  const elapsedMs = lastSubmittedAt ? Date.now() - lastSubmittedAt : 0;

  if (elapsedMs < 8_000) {
    return {
      label: "Analyzing",
      detail: "Processing your query...",
    };
  }

  if (elapsedMs < 20_000) {
    return {
      label: "Researching",
      detail: "Gathering relevant regulations and data...",
    };
  }

  return {
    label: "Writing",
    detail: "Composing the response...",
  };
}
