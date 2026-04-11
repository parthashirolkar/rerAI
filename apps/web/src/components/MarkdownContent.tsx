import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownContentProps = {
  children: string;
  compact?: boolean;
};

export function MarkdownContent({ children, compact = false }: MarkdownContentProps) {
  return (
    <div className={compact ? "markdown-body markdown-compact" : "markdown-body"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
