import type { ReactNode } from "react";
import { FileText } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { MarkdownContent } from "./MarkdownContent";
import type { ParsedPermitReport } from "@/lib/report";

type ReportPanelProps = {
  error: unknown;
  report: ParsedPermitReport;
};

export function ReportPanel({ error, report }: ReportPanelProps) {
  return (
    <ScrollArea className="h-full">
      <div className="px-5 py-6">
        <div className="flex items-center gap-2">
          <FileText className="size-4 text-muted-foreground" />
          <h3 className="font-serif text-base font-semibold">Report</h3>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Structured breakdown from the latest analysis
        </p>

        <Separator className="my-4" />

        <div className="space-y-3">
          {error ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
              <p className="text-xs font-medium text-destructive">
                Connection error
              </p>
              <p className="mt-1 text-xs text-destructive/80">
                {error instanceof Error ? error.message : String(error)}
              </p>
            </div>
          ) : null}

          {report.summary ? (
            <SectionCard title="Summary">
              <MarkdownContent compact>{report.summary}</MarkdownContent>
            </SectionCard>
          ) : null}

          {report.sections.map((section) => (
            <SectionCard key={section.title} title={section.title}>
              <MarkdownContent compact>{section.body}</MarkdownContent>
            </SectionCard>
          ))}

          {!report.sections.length && !report.summary ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center">
              <Skeleton className="size-10 rounded-full" />
              <p className="text-xs text-muted-foreground">
                Report sections will appear here after analysis
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </ScrollArea>
  );
}

function SectionCard({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs font-semibold text-foreground">{title}</p>
      <div className="mt-2">{children}</div>
    </div>
  );
}
