// Library-Playground batch picker — claude.ai port.
//
// Optional richer view for batch confirmation when per-book context
// (cover-style cards, content flags, longer pitches) helps the reader
// decide.  The DEFAULT batch-confirmation surface is now native
// multi-select via AskUserQuestion in chat — this artifact is opt-in.
//
// Pure renderer.  No window.storage, no persistence, no preflight.
// Selections come back through the reader's chat reply (they tap the
// cards to mark which they want, then type the picks back in chat).
// The librarian skills no longer rely on artifact storage round-trips.
//
// Constraints honoured (see CLAUDE.md librarian invariants 5 & 8):
//  - All cards render identically — no deep-cut differentiation in
//    styling, ordering, labels, or sentence count.
//  - The artifact never names "deep cut", "hidden gem", "indie pick",
//    or any internal vocabulary.

import React, { useState } from "react";

const SAMPLE_BATCH = {
  prompt: "Which of these horror picks belong in your pool?",
  books: [
    {
      title: "Between Two Fires",
      author: "Christopher Buehlman",
      pages: 432,
      pitch:
        "Cosmic horror in plague-era France: a fallen angel and an orphan girl on the road in 1348. " +
        "Lyrical grimdark prose, tonally adjacent to Wolfe and Kay. Audio is excellent (Erikson narrates).",
      content_flags: ["graphic violence", "religious horror"],
    },
    {
      title: "The Lesser Dead",
      author: "Christopher Buehlman",
      pages: 249,
      pitch:
        "1970s NYC vampire novel narrated by a teenage subway-tunnel vampire. " +
        "Same Buehlman voice in a faster, leaner package — good if you want the tone without another 400-pager.",
      content_flags: [],
    },
    {
      title: "Mountain Fast",
      author: "Brian Lerner",
      pages: 314,
      pitch:
        "Monastic siege horror set in a remote alpine abbey, 4.4/287 reviews — small audience, strong love. " +
        "Pulled because of your monastic-settings note in your profile.",
      content_flags: [],
    },
    {
      title: "The Shining",
      author: "Stephen King",
      pages: 355,
      pitch:
        "Hotel-isolation horror; you've read deep King but not this one. Worth it for the Torrance interiority alone.",
      content_flags: ["domestic violence", "child endangerment"],
    },
  ],
};

function bookKey(book, idx) {
  return `${(book.title || "").toLowerCase()}|${(book.author || "").toLowerCase()}|${idx}`;
}

export default function BatchPicker(props) {
  const batch = props.batch || SAMPLE_BATCH;
  const books = batch.books || [];
  const [selected, setSelected] = useState(() => new Set());

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const selectedTitles = books
    .map((b, i) => ({ b, id: bookKey(b, i) }))
    .filter(({ id }) => selected.has(id))
    .map(({ b }) => `${b.title} — ${b.author}`);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-3xl px-4 pb-32 pt-6 sm:pt-10">
        <header className="space-y-2">
          <h1 className="text-xl font-semibold leading-tight sm:text-2xl">
            {batch.prompt || "Which of these belong in your pool?"}
          </h1>
          {batch.subtitle && (
            <p className="text-sm text-slate-600 sm:text-base">{batch.subtitle}</p>
          )}
          <p className="text-sm text-slate-500">
            Tap each book you want.  When you're done, type the picks back
            in chat (or copy from the panel below) — the librarian uses
            your chat reply, not this artifact.
          </p>
        </header>

        <ul className="mt-6 grid gap-4 sm:grid-cols-1">
          {books.map((book, idx) => {
            const id = bookKey(book, idx);
            const isOn = selected.has(id);
            return (
              <li key={id}>
                <BookCard
                  book={book}
                  selected={isOn}
                  onToggle={() => toggle(id)}
                />
              </li>
            );
          })}
        </ul>

        <SelectionEcho titles={selectedTitles} total={books.length} />
      </div>
    </div>
  );
}

function BookCard({ book, selected, onToggle }) {
  const flags = Array.isArray(book.content_flags) ? book.content_flags : [];
  const ringClass = selected
    ? "ring-2 ring-emerald-500"
    : "ring-1 ring-slate-200";

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={selected}
      className={[
        "w-full rounded-2xl bg-white p-4 text-left shadow-sm transition",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400",
        ringClass,
        "cursor-pointer hover:shadow-md",
      ].join(" ")}
    >
      <div className="flex items-start gap-4">
        <Checkbox checked={selected} />
        <div className="flex-1 space-y-2">
          <div>
            <h2 className="text-base font-semibold leading-snug sm:text-lg">
              {book.title}
            </h2>
            <p className="text-sm text-slate-600">
              {book.author}
              {book.pages ? <> · {book.pages} pp</> : null}
            </p>
          </div>
          <p className="text-sm leading-relaxed text-slate-800 sm:text-base">
            {book.pitch}
          </p>
          {flags.length > 0 && (
            <p className="text-xs italic text-slate-500">
              Notes: {flags.join(", ")}.
            </p>
          )}
        </div>
      </div>
    </button>
  );
}

function Checkbox({ checked }) {
  return (
    <span
      className={[
        "mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center",
        "rounded-md border-2 transition",
        checked
          ? "border-emerald-500 bg-emerald-500 text-white"
          : "border-slate-300 bg-white text-transparent",
      ].join(" ")}
      aria-hidden="true"
    >
      <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4">
        <path
          d="M4 10.5l4 4 8-9"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

function SelectionEcho({ titles, total }) {
  if (titles.length === 0) {
    return (
      <p className="mt-8 text-sm text-slate-500">
        Nothing selected yet.  Reply in chat with the picks once you've
        chosen ({total} books to choose from).
      </p>
    );
  }
  const text = titles.join("\n");
  return (
    <div className="mt-8 rounded-2xl bg-white p-4 ring-1 ring-slate-200">
      <p className="mb-2 text-sm font-medium text-slate-700">
        {titles.length} selected — copy this back into chat:
      </p>
      <pre className="whitespace-pre-wrap rounded-lg bg-slate-100 p-3 text-xs font-mono text-slate-800">
        {text}
      </pre>
    </div>
  );
}
