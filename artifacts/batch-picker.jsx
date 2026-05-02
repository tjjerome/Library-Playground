// Library-Playground batch picker — claude.ai port.
//
// Renders a 4-card multi-select for the librarian-build-batches skill.
// Persists selections to `window.storage` under `batch:<batchId>` so the
// model can read them back on its next turn, and appends a digest to a
// `pending_flush` queue so a session that ends abruptly (F4 in
// UX_DESIGN.md) leaves the selections recoverable next session.
//
// IMPORTANT: window.storage operations only succeed on PUBLISHED
// artifacts.  In the preview/edit pane they silently no-op.  This
// component shows a soft warning when storage round-trips fail, so the
// user notices the artifact needs republishing.
//
// Constraints honoured (see CLAUDE.md librarian invariants 5 & 8):
//  - All four cards render identically — no deep-cut differentiation
//    in styling, ordering, labels, or sentence count.
//  - The artifact never names "deep cut", "hidden gem", "indie pick",
//    or any internal vocabulary.

import React, { useEffect, useMemo, useRef, useState } from "react";

const STORAGE_VERSION = 1;
const PENDING_FLUSH_KEY = "pending_flush";

// Stable id for a book.  Matches the shape the helper script uses for
// ledger keys: lowercased, whitespace-collapsed "title|author".
function bookId(book) {
  const t = (book.title || "").trim().toLowerCase().replace(/\s+/g, " ");
  const a = (book.author || "").trim().toLowerCase().replace(/\s+/g, " ");
  return `${t}|${a}`;
}

const SAMPLE_BATCH = {
  batch_id: "sample-horror-2026-05-02",
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

// Read storage with a tolerant signature (the API returns either {value}
// or null).  Returns null on failure or unpublished-artifact silence.
async function safeGet(key) {
  try {
    if (!window.storage || typeof window.storage.get !== "function") return null;
    const result = await window.storage.get(key);
    if (!result) return null;
    if (typeof result.value === "string") {
      try {
        return JSON.parse(result.value);
      } catch {
        return null;
      }
    }
    return result.value ?? null;
  } catch {
    return null;
  }
}

async function safeSet(key, value) {
  try {
    if (!window.storage || typeof window.storage.set !== "function") return false;
    await window.storage.set(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

// Append a digest of this batch's selections to the persistent
// `pending_flush` queue so a future session can complete the
// Drive flush even if the current chat ended abruptly.
async function enqueuePendingFlush(payload) {
  const existing = (await safeGet(PENDING_FLUSH_KEY)) || [];
  const queue = Array.isArray(existing) ? existing : [];
  queue.push(payload);
  await safeSet(PENDING_FLUSH_KEY, queue);
}

export default function BatchPicker(props) {
  const batch = props.batch || SAMPLE_BATCH;
  const onSavedProp = props.onSaved;
  const storageEnabled = props.storageEnabled !== false;

  const books = batch.books || [];
  const batchId = batch.batch_id || `batch-${Date.now()}`;
  const storageKey = `batch:${batchId}`;

  // Selection state — keyed by stable bookId.
  const [selected, setSelected] = useState(() => new Set());
  const [phase, setPhase] = useState("loading"); // loading | editing | saving | saved
  const [storageWarning, setStorageWarning] = useState(false);
  const loadedRef = useRef(false);

  // Restore prior selections (if the user already saved this batch and
  // refreshed the page).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!storageEnabled) {
        setPhase("editing");
        return;
      }
      const prior = await safeGet(storageKey);
      if (cancelled) return;
      if (prior && Array.isArray(prior.selected)) {
        setSelected(new Set(prior.selected));
        if (prior.committed) {
          setPhase("saved");
          loadedRef.current = true;
          return;
        }
      }
      setPhase("editing");
    })();
    return () => {
      cancelled = true;
    };
  }, [storageKey, storageEnabled]);

  function toggle(id) {
    if (phase !== "editing") return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSave() {
    if (phase !== "editing") return;
    setPhase("saving");
    const selectedIds = Array.from(selected);
    const allIds = books.map(bookId);
    const rejectedIds = allIds.filter((i) => !selectedIds.includes(i));

    // Map back to {title, author, status} records the helper expects.
    const idToBook = new Map(books.map((b) => [bookId(b), b]));
    const records = [
      ...selectedIds.map((id) => ({ ...idToBook.get(id), status: "selected" })),
      ...rejectedIds.map((id) => ({ ...idToBook.get(id), status: "rejected" })),
    ].map((r) => ({
      title: r.title,
      author: r.author,
      pages: r.pages,
      status: r.status,
    }));

    const payload = {
      version: STORAGE_VERSION,
      batch_id: batchId,
      selected: selectedIds,
      rejected: rejectedIds,
      records,
      committed: true,
      saved_at: new Date().toISOString(),
    };

    const ok = storageEnabled ? await safeSet(storageKey, payload) : true;
    if (storageEnabled) {
      // Best-effort confirmation read — if it comes back empty, the
      // artifact is probably unpublished and the model won't see this.
      const verify = await safeGet(storageKey);
      if (!verify) setStorageWarning(true);
      await enqueuePendingFlush({
        batch_id: batchId,
        records,
        saved_at: payload.saved_at,
      });
    }

    setPhase("saved");
    if (typeof onSavedProp === "function") onSavedProp(payload);
    if (!ok && storageEnabled) setStorageWarning(true);
  }

  const editing = phase === "editing";
  const saved = phase === "saved";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-3xl px-4 pb-32 pt-6 sm:pt-10">
        <Header
          prompt={batch.prompt || "Which of these belong in your pool?"}
          subtitle={batch.subtitle}
          saved={saved}
        />

        {storageWarning && <StorageWarning />}

        <ul className="mt-6 grid gap-4 sm:grid-cols-1">
          {books.map((book) => {
            const id = bookId(book);
            const isOn = selected.has(id);
            return (
              <li key={id}>
                <BookCard
                  book={book}
                  selected={isOn}
                  disabled={!editing}
                  onToggle={() => toggle(id)}
                />
              </li>
            );
          })}
        </ul>

        {saved && <SavedBanner count={selected.size} total={books.length} />}
      </div>

      <SaveBar
        phase={phase}
        selectedCount={selected.size}
        totalCount={books.length}
        onSave={handleSave}
      />
    </div>
  );
}

function Header({ prompt, subtitle, saved }) {
  return (
    <header className="space-y-2">
      <h1 className="text-xl font-semibold leading-tight sm:text-2xl">
        {prompt}
      </h1>
      {subtitle && (
        <p className="text-sm text-slate-600 sm:text-base">{subtitle}</p>
      )}
      {!saved && (
        <p className="text-sm text-slate-500">
          Tap each book you want in your pool.  Unselected books aren't
          rejected — they just aren't added this round.
        </p>
      )}
    </header>
  );
}

function BookCard({ book, selected, disabled, onToggle }) {
  const flags = Array.isArray(book.content_flags) ? book.content_flags : [];
  const ringClass = selected
    ? "ring-2 ring-emerald-500"
    : "ring-1 ring-slate-200";
  const opacityClass = disabled && !selected ? "opacity-70" : "";

  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={selected}
      className={[
        "w-full rounded-2xl bg-white p-4 text-left shadow-sm transition",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400",
        ringClass,
        opacityClass,
        disabled ? "cursor-default" : "cursor-pointer hover:shadow-md",
      ].join(" ")}
    >
      <div className="flex items-start gap-4">
        <Checkbox checked={selected} disabled={disabled} />
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

function Checkbox({ checked, disabled }) {
  return (
    <span
      className={[
        "mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center",
        "rounded-md border-2 transition",
        checked
          ? "border-emerald-500 bg-emerald-500 text-white"
          : "border-slate-300 bg-white text-transparent",
        disabled ? "border-slate-200" : "",
      ].join(" ")}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 20 20"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="h-4 w-4"
      >
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

function SavedBanner({ count, total }) {
  return (
    <div className="mt-6 rounded-2xl bg-emerald-50 p-4 ring-1 ring-emerald-200">
      <p className="text-sm font-medium text-emerald-900">
        Saved — back to chat.
      </p>
      <p className="mt-1 text-sm text-emerald-800">
        {count} of {total} added to your pool.  The librarian will pick this
        up on its next turn.
      </p>
    </div>
  );
}

function StorageWarning() {
  return (
    <div className="mt-4 rounded-2xl bg-amber-50 p-4 ring-1 ring-amber-200">
      <p className="text-sm font-medium text-amber-900">
        Heads up — your selections may not be saving.
      </p>
      <p className="mt-1 text-sm text-amber-800">
        This artifact has to be published for storage to work.  Click the
        Publish button on the artifact panel, then refresh this view and
        try again.
      </p>
    </div>
  );
}

function SaveBar({ phase, selectedCount, totalCount, onSave }) {
  const editing = phase === "editing";
  const saving = phase === "saving";
  const saved = phase === "saved";

  let label;
  if (saving) label = "Saving…";
  else if (saved) label = "Saved";
  else if (selectedCount === 0)
    label = "Save — none of these for now";
  else if (selectedCount === totalCount)
    label = `Save all ${totalCount}`;
  else label = `Save ${selectedCount} of ${totalCount}`;

  return (
    <div className="fixed inset-x-0 bottom-0 z-10 border-t border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
        <p className="text-sm text-slate-600">
          {saved
            ? "You can close this view."
            : `${selectedCount} selected`}
        </p>
        <button
          type="button"
          onClick={onSave}
          disabled={!editing}
          className={[
            "rounded-xl px-4 py-3 text-sm font-semibold transition",
            "min-h-[44px]",
            editing
              ? "bg-emerald-600 text-white hover:bg-emerald-700"
              : "bg-slate-200 text-slate-500",
          ].join(" ")}
        >
          {label}
        </button>
      </div>
    </div>
  );
}
