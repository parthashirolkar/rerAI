import { KeyboardEvent, FormEvent, useRef, useCallback, useEffect, useState } from "react";
import { ArrowUp, Loader2, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ComposerProps = {
  busy: boolean;
  canStop?: boolean;
  draft: string;
  isStopping?: boolean;
  onChange: (value: string) => void;
  onStop?: () => Promise<void>;
  onSubmit: (value: string) => Promise<void>;
};

export function Composer({
  busy,
  canStop = false,
  draft,
  isStopping = false,
  onChange,
  onStop,
  onSubmit,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [lineCount, setLineCount] = useState(1);
  const [isExpanding, setIsExpanding] = useState(false);

  const syncHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight, 160);
    el.style.height = `${next}px`;
    const lines = Math.ceil(el.scrollHeight / 22);
    setLineCount(Math.max(1, lines));
  }, []);

  useEffect(() => {
    syncHeight();
  }, [draft, syncHeight]);

  useEffect(() => {
    if (lineCount > 1) {
      setIsExpanding(true);
      const t = setTimeout(() => setIsExpanding(false), 400);
      return () => clearTimeout(t);
    }
  }, [lineCount]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onSubmit(draft);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void onSubmit(draft);
    }
  };

  const expanded = lineCount > 2;
  const multiLine = lineCount > 1;

  return (
    <div className="border-t bg-background/80 backdrop-blur-sm px-4 py-3">
      <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
        <div
          className={`composer-shell relative flex items-end gap-2 border bg-background px-4 py-2.5
            focus-within:border-ring
            ${expanded ? "rounded-xl" : "rounded-2xl"}
            ${isExpanding ? "composer-expand" : ""}
          `}
          style={{
            boxShadow: multiLine
              ? "0 0 0 3px hsl(155 22% 30% / 0.12), 0 4px 20px -4px hsl(155 18% 30% / 0.15)"
              : undefined,
            transition: "border-radius 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.35s ease-out",
          }}
        >
          <Textarea
            ref={textareaRef}
            className="max-h-40 min-h-[1.5rem] flex-1 resize-none border-0 bg-transparent p-0 text-sm leading-relaxed shadow-none focus-visible:ring-0 focus-visible:border-0"
            disabled={busy}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a plot, address, or regulation..."
            rows={1}
            value={draft}
          />
          {canStop ? (
            <Button
              size="icon-sm"
              aria-label="Stop generating"
              disabled={isStopping}
              type="button"
              className={multiLine ? "mb-0.5" : ""}
              onClick={() => void onStop?.()}
            >
              {isStopping ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Square className="size-3.5 fill-current" />
              )}
            </Button>
          ) : (
            <Button
              size="icon-sm"
              aria-label="Send message"
              disabled={busy || !draft.trim()}
              type="submit"
              className={multiLine ? "mb-0.5" : ""}
            >
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ArrowUp className="size-4" />
              )}
            </Button>
          )}
        </div>
        <p className="mt-1.5 text-center text-[10px] text-muted-foreground/60">
          Shift+Enter for new line
        </p>
      </form>
    </div>
  );
}
