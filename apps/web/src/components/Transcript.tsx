import { useEffect, useRef } from "react";
import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarkdownContent } from "./MarkdownContent";
import type { ChatMessage, ConversationTurn } from "@/lib/messages";

type TranscriptProps = {
  hasMessages: boolean;
  isStreaming: boolean;
  showThinking: boolean;
  messages: ChatMessage[];
  turns?: ConversationTurn[];
  sampleQueries: string[];
  onRetryTurn?: (turnId: string) => void;
  onUseSample: (query: string) => void;
};

export function Transcript({
  hasMessages,
  isStreaming,
  showThinking,
  messages,
  turns,
  sampleQueries,
  onRetryTurn,
  onUseSample,
}: TranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const shouldFollowRef = useRef(true);

  const orderedTurns = [...(turns ?? [])].sort(
    (left, right) => left.turnPosition - right.turnPosition,
  );
  const transcriptItemCount =
    orderedTurns.length > 0
      ? orderedTurns.reduce(
          (count, turn) => count + 1 + turn.assistantMessages.length,
          0,
        )
      : messages.length;

  useEffect(() => {
    const scrollEl = scrollRef.current;
    if (!scrollEl || !shouldFollowRef.current) return;
    scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: "smooth" });
  }, [transcriptItemCount, showThinking]);

  return (
    <div
      ref={scrollRef}
      className="min-h-0 flex-1 overflow-y-auto"
      onScroll={(event) => {
        const element = event.currentTarget;
        shouldFollowRef.current =
          element.scrollHeight - element.scrollTop - element.clientHeight < 96;
      }}
    >
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
          {orderedTurns.length > 0
            ? orderedTurns.map((turn, turnIndex) => {
                const assistantMessages = [...turn.assistantMessages].sort(
                  (left, right) => left.messagePosition - right.messagePosition,
                );
                const isLastTurn = turnIndex === orderedTurns.length - 1;
                return (
                  <div key={turn.turnId} className="contents">
                    <div className="flex justify-end">
                      <div className="flex flex-col items-end gap-1">
                        <div className="chat-bubble-user">
                          <p className="whitespace-pre-wrap">{turn.userContent}</p>
                        </div>
                        {turn.status === "failed" && onRetryTurn ? (
                          <Button
                            variant="ghost"
                            size="xs"
                            onClick={() => onRetryTurn(turn.turnId)}
                          >
                            Try again
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    {assistantMessages.length > 0 ? (
                      <div className="flex justify-start">
                        <div
                          className="chat-bubble-assistant"
                          data-testid="assistant-response"
                        >
                          {assistantMessages.map((message, messageIndex) => {
                            const showStreamingCursor =
                              isStreaming &&
                              isLastTurn &&
                              messageIndex === assistantMessages.length - 1;
                            return (
                              <div key={message.id} className="assistant-message-block">
                                {message.canonicalContent ? (
                                  <MarkdownContent>
                                    {message.canonicalContent}
                                  </MarkdownContent>
                                ) : null}
                                {message.displayOnlyContent ? (
                                  <MarkdownContent>
                                    {message.displayOnlyContent}
                                  </MarkdownContent>
                                ) : null}
                                {showStreamingCursor ? (
                                  <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-foreground/50 align-text-bottom" />
                                ) : null}
                              </div>
                            );
                          })}
                          {turn.status === "failed" ? (
                            <p className="mt-2 text-xs text-destructive">
                              Failed{turn.errorMessage ? `: ${turn.errorMessage}` : ""}
                            </p>
                          ) : null}
                          {turn.status === "cancelled" ? (
                            <p className="mt-2 text-xs text-muted-foreground">Stopped</p>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })
            : messages.map((message, index) => {
                const isAssistant = message.role === "assistant";
                const isLastMessage = index === messages.length - 1;
                const showStreamingCursor =
                  isAssistant && isLastMessage && isStreaming;
                return (
                  <div
                    key={message.id ?? message._id ?? `msg-${index}`}
                    className={`flex ${isAssistant ? "justify-start" : "justify-end"}`}
                  >
                    <div
                      className={
                        isAssistant
                          ? "chat-bubble-assistant"
                          : "chat-bubble-user"
                      }
                    >
                      {isAssistant ? (
                        <>
                          {message.content ? (
                            <MarkdownContent>{message.content}</MarkdownContent>
                          ) : null}
                          {showStreamingCursor && (
                            <span className="inline-block ml-0.5 w-1.5 h-4 bg-foreground/50 animate-pulse align-text-bottom rounded-sm" />
                          )}
                        </>
                      ) : (
                        <p className="whitespace-pre-wrap">
                          {message.content}
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
