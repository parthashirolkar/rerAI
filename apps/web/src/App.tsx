import { FormEvent, useState } from "react";

import { langgraphClient } from "./lib/langgraphClient";

type ChatLine = {
  role: "user" | "assistant";
  content: string;
};

export default function App() {
  const [threadId, setThreadId] = useState<string>("");
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [busy, setBusy] = useState(false);

  const ensureThread = async () => {
    if (threadId) {
      return threadId;
    }
    const thread = await langgraphClient.threads.create();
    setThreadId(thread.thread_id);
    return thread.thread_id;
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || busy) {
      return;
    }

    const content = text.trim();
    setText("");
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", content }]);

    try {
      const id = await ensureThread();
      const run = await langgraphClient.runs.create(id, "rerai", {
        input: {
          messages: [{ role: "user", content }],
        },
      });

      const result = await langgraphClient.runs.wait(id, run.run_id);
      const outputMessages = (result as { messages?: { content?: string }[] }).messages;
      const reply = outputMessages?.[outputMessages.length - 1]?.content;

      if (reply) {
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${String(error)}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-wash-gradient p-6 text-ink md:p-10">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 rounded-3xl border border-black/10 bg-white/80 p-6 shadow-xl backdrop-blur">
        <header>
          <p className="font-display text-3xl tracking-tight">rerAI</p>
          <p className="font-body text-sm text-ink/70">
            LangGraph API client playground
          </p>
          <p className="font-mono text-xs text-ink/60">
            thread: {threadId || "(new thread on first message)"}
          </p>
        </header>

        <main className="h-[55vh] overflow-y-auto rounded-2xl bg-sage/40 p-4">
          <div className="flex flex-col gap-3">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  message.role === "user"
                    ? "ml-auto bg-fern text-white"
                    : "mr-auto bg-white text-ink"
                }`}
              >
                {message.content}
              </div>
            ))}
            {!messages.length && (
              <p className="text-sm text-ink/60">
                Ask about permit feasibility for a Pune location to start.
              </p>
            )}
          </div>
        </main>

        <form className="flex gap-3" onSubmit={onSubmit}>
          <input
            className="w-full rounded-xl border border-black/10 bg-white px-4 py-3 text-sm outline-none ring-clay/30 placeholder:text-ink/40 focus:ring"
            disabled={busy}
            onChange={(event) => setText(event.target.value)}
            placeholder="Enter address, survey number, or coordinates"
            value={text}
          />
          <button
            className="rounded-xl bg-clay px-4 py-3 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy}
            type="submit"
          >
            {busy ? "Working..." : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
