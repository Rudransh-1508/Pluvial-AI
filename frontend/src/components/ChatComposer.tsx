"use client";

import { useEffect, useRef } from "react";

export interface ChatTurn {
  id: number;
  side: "user" | "assistant" | "system" | "tool";
  text: string;
}

/* The chat model writes in light markdown — **bold** and "- " bullets — and
   nothing here ever rendered it, so replies showed literal asterisks and
   dashes. This covers exactly what the model actually produces; it is not a
   general markdown renderer. */
function renderInline(text: string, keyPrefix: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={`${keyPrefix}-${i}`} className="font-semibold text-bone">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <span key={`${keyPrefix}-${i}`}>{part}</span>
    ),
  );
}

function ChatText({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: { type: "p" | "ul"; lines: string[] }[] = [];
  for (const line of lines) {
    const isBullet = /^\s*[-•]\s+/.test(line);
    if (line.trim() === "") continue;
    const last = blocks[blocks.length - 1];
    if (isBullet) {
      const item = line.replace(/^\s*[-•]\s+/, "");
      if (last?.type === "ul") last.lines.push(item);
      else blocks.push({ type: "ul", lines: [item] });
    } else {
      if (last?.type === "p") last.lines.push(line);
      else blocks.push({ type: "p", lines: [line] });
    }
  }
  return (
    <>
      {blocks.map((block, i) =>
        block.type === "ul" ? (
          <ul key={i} className="my-1.5 list-disc space-y-1 pl-4">
            {block.lines.map((line, j) => (
              <li key={j}>{renderInline(line, `${i}-${j}`)}</li>
            ))}
          </ul>
        ) : (
          <p key={i} className={i > 0 ? "mt-1.5" : undefined}>
            {block.lines.map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {renderInline(line, `${i}-${j}`)}
              </span>
            ))}
          </p>
        ),
      )}
    </>
  );
}

export interface PendingQuote {
  pending_id: string;
  kind: "sample_point" | "analyze_location";
  quoted_credits: number;
  label: string;
  location_id?: number;
  sample_id?: number;
}

/* The chat can propose a purchase; it can never make one. A `quote` event
   renders this, and the credits leave the account when — and only when —
   someone presses the button. Identical to the address box's gate, because
   it is the same gate: an agent may ask, a person authorises. */
function QuoteGate({
  quote,
  onConfirm,
  onDismiss,
  busy,
}: {
  quote: PendingQuote;
  onConfirm: () => void;
  onDismiss: () => void;
  busy: boolean;
}) {
  return (
    <div className="rounded border border-moisture/45 bg-moisture/8 px-3 py-2.5">
      <p className="eyebrow">quote · nothing spent yet</p>
      <p className="mt-1 text-[13px] leading-snug text-bone">{quote.label}</p>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="rounded bg-moisture px-3 py-1.5 text-[12.5px] font-medium text-ground-900 transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Fetching…" : `Confirm ${quote.quoted_credits} credits`}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          disabled={busy}
          className="rounded px-2.5 py-1.5 text-[12.5px] text-bone-faint transition-colors hover:text-bone disabled:opacity-40"
        >
          Not now
        </button>
      </div>
    </div>
  );
}

export function ChatComposer({
  turns,
  quote,
  busy,
  disabled,
  onSend,
  onConfirm,
  onDismissQuote,
}: {
  turns: ChatTurn[];
  quote: PendingQuote | null;
  busy: boolean;
  disabled: boolean;
  onSend: (message: string) => void;
  onConfirm: () => void;
  onDismissQuote: () => void;
}) {
  const input = useRef<HTMLInputElement | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns.length, quote]);

  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-ground-700 bg-ground-850">
      <header className="border-b border-ground-700 px-3.5 py-2.5">
        <h3 className="display text-[14px] text-bone">Ask about this ground</h3>
        <p className="mt-0.5 text-[11.5px] leading-snug text-bone-faint">
          {disabled
            ? "Opens once the three rulings land."
            : "Answers from evidence already fetched, or proposes fetching more."}
        </p>
      </header>

      {turns.length > 0 && (
        <div ref={scroller} className="max-h-96 min-h-0 flex-1 space-y-2.5 overflow-y-auto px-3.5 py-2.5">
          {turns.map((turn) => (
            <div
              key={turn.id}
              className={
                turn.side === "user"
                  ? "border-l-2 border-bone-faint pl-2.5 text-[13px] text-bone"
                  : turn.side === "tool"
                    ? "data pl-2.5 text-[12px] text-bone-faint"
                    : turn.side === "system"
                      ? "pl-2.5 text-[12.5px] text-moisture"
                      : "border-l-2 border-moisture/50 pl-2.5 text-[13px] leading-relaxed text-bone-dim"
              }
            >
              {turn.side === "tool" && <span aria-hidden>▸ </span>}
              {turn.side === "assistant" ? <ChatText text={turn.text} /> : turn.text}
            </div>
          ))}
          {quote && (
            <QuoteGate quote={quote} onConfirm={onConfirm} onDismiss={onDismissQuote} busy={busy} />
          )}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const value = input.current?.value.trim();
          if (!value) return;
          onSend(value);
          if (input.current) input.current.value = "";
        }}
        className="flex gap-2 border-t border-ground-700 p-2.5"
      >
        <label htmlFor="chat" className="sr-only">
          Ask about this ground
        </label>
        <input
          id="chat"
          ref={input}
          disabled={disabled || busy}
          placeholder={disabled ? "Waiting for the rulings…" : "Why did you veto that point?"}
          className="flex-1 rounded border border-ground-700 bg-ground-900 px-3 py-2 text-[13px] text-bone placeholder:text-bone-faint focus:border-moisture focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || busy}
          className="rounded border border-ground-700 px-3 py-2 text-[13px] text-bone-dim transition-colors hover:bg-ground-800 hover:text-bone disabled:opacity-40"
        >
          {busy ? "…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
