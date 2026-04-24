import { useEffect, useRef } from "react";
import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MarkdownContent } from "./MarkdownContent";
import {
  extractMessageText,
  getMessageKey,
  isAssistantMessage,
} from "@/lib/messages";

type TranscriptProps = {
  hasMessages: boolean;
  isStreaming: boolean;
  showThinking: boolean;
  messages: unknown[];
  progressDetail: string;
  sampleQueries: string[];
  onUseSample: (query: string) => void;
};

export function Transcript({
  hasMessages,
  isStreaming,
  showThinking,
  messages,
  progressDetail,
  sampleQueries,
  onUseSample,
}: TranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;
    scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: "smooth" });
  }, [messages.length, showThinking]);

  return (
    <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-5 py-6">
        {!hasMessages ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="mb-8 text-center">
              <h2 className="font-serif text-2xl font-semibold text-foreground/90">
                How can I help?
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Ask about permit feasibility, site regulations, or development
                potential for any plot in Pune.
              </p>
            </div>
            <div className="flex w-full max-w-lg flex-col gap-2">
              {sampleQueries.map((sample) => (
                <Button
                  key={sample}
                  variant="outline"
                  className="h-auto justify-start whitespace-normal py-3 text-left text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => onUseSample(sample)}
                >
                  <MessageSquare className="mr-2 size-3.5 shrink-0" />
                  {sample}
                </Button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="flex flex-col gap-4">
          {messages.map((message, index) => {
            const assistant = isAssistantMessage(message);
            const isLastMessage = index === messages.length - 1;
            const text = extractMessageText(message);
            const showStreamingCursor = assistant && isLastMessage && isStreaming;
            return (
              <div
                key={getMessageKey(message, index)}
                className={`flex ${assistant ? "justify-start" : "justify-end"}`}
              >
                <div
                  className={
                    assistant
                      ? "chat-bubble-assistant"
                      : "chat-bubble-user"
                  }
                >
                  {assistant ? (
                    <>
                      {text ? (
                        <MarkdownContent>{text}</MarkdownContent>
                      ) : null}
                      {showStreamingCursor && (
                        <span className="inline-block ml-0.5 w-1.5 h-4 bg-foreground/50 animate-pulse align-text-bottom rounded-sm" />
                      )}
                    </>
                  ) : (
                    <p className="whitespace-pre-wrap">
                      {text}
                    </p>
                  )}
                </div>
              </div>
            );
          })}

          {showThinking ? (
            <div className="flex justify-start">
              <div className="chat-bubble-assistant flex items-center gap-1 py-4">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
