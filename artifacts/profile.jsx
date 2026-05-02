// Library-Playground profile artifact — claude.ai port.
//
// Holds the reader's `Profile.md` content in `window.storage` and
// renders it.  Skills (build-setup, build-batches, build-finish,
// quickref) write here via `window.storage.set("profile", "...")`;
// the artifact is the persistence layer the reader sees.
//
// Storage key: `profile`
// Stored value: { version: 1, content: "<markdown text>", updated_at: "<ISO>" }
//
// IMPORTANT: window.storage only works on PUBLISHED artifacts.  Setup
// step 8 in SETUP.md walks through the publish flow.  If the storage
// round-trip fails, the artifact shows a soft warning so the reader
// notices the artifact needs republishing.

import React, { useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "profile";
const STORAGE_VERSION = 1;
const SEED_PROFILE = `# Reader Profile

_Living memory — updated throughout reading-list builds._
`;

async function safeGet(key) {
  try {
    if (!window.storage || typeof window.storage.get !== "function") return null;
    const r = await window.storage.get(key);
    if (!r) return null;
    if (typeof r.value === "string") {
      try { return JSON.parse(r.value); } catch { return null; }
    }
    return r.value ?? null;
  } catch { return null; }
}

async function safeSet(key, value) {
  try {
    if (!window.storage || typeof window.storage.set !== "function") return false;
    await window.storage.set(key, JSON.stringify(value));
    return true;
  } catch { return false; }
}

// Lightweight markdown renderer — headings, bullets, paragraphs,
// horizontal rules.  Tables and code blocks pass through as
// preformatted text (good enough for Profile.md).
function MarkdownView({ source }) {
  const blocks = useMemo(() => parseMarkdown(source || ""), [source]);
  return (
    <div className="prose prose-slate max-w-none">
      {blocks.map((b, i) => renderBlock(b, i))}
    </div>
  );
}

function parseMarkdown(text) {
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^#{1,6}\s/.test(line)) {
      const m = line.match(/^(#{1,6})\s+(.*)$/);
      blocks.push({ type: "heading", level: m[1].length, text: m[2] });
      i++;
    } else if (/^\s*[-*]\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push({ type: "bullets", items });
    } else if (/^\s*\|/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        rows.push(lines[i]);
        i++;
      }
      blocks.push({ type: "raw", text: rows.join("\n") });
    } else if (/^---+$/.test(line.trim())) {
      blocks.push({ type: "hr" });
      i++;
    } else if (line.trim() === "") {
      i++;
    } else {
      const para = [line];
      i++;
      while (
        i < lines.length &&
        lines[i].trim() !== "" &&
        !/^#{1,6}\s/.test(lines[i]) &&
        !/^\s*[-*]\s/.test(lines[i]) &&
        !/^\s*\|/.test(lines[i])
      ) {
        para.push(lines[i]);
        i++;
      }
      blocks.push({ type: "paragraph", text: para.join(" ") });
    }
  }
  return blocks;
}

function renderInline(text) {
  // Italics _x_ and bold **x** — only the cases Profile.md uses.
  const parts = [];
  let rest = text;
  let key = 0;
  while (rest.length > 0) {
    const bold = rest.match(/^\*\*([^*]+)\*\*/);
    if (bold) {
      parts.push(<strong key={key++}>{bold[1]}</strong>);
      rest = rest.slice(bold[0].length);
      continue;
    }
    const em = rest.match(/^_([^_]+)_/);
    if (em) {
      parts.push(<em key={key++}>{em[1]}</em>);
      rest = rest.slice(em[0].length);
      continue;
    }
    parts.push(rest[0]);
    rest = rest.slice(1);
  }
  return parts;
}

function renderBlock(b, key) {
  if (b.type === "heading") {
    const Tag = `h${b.level}`;
    const cls = b.level === 1
      ? "text-2xl font-bold mt-6 mb-3"
      : b.level === 2
        ? "text-xl font-semibold mt-5 mb-2 border-b border-slate-200 pb-1"
        : "text-base font-semibold mt-4 mb-2";
    return <Tag key={key} className={cls}>{renderInline(b.text)}</Tag>;
  }
  if (b.type === "bullets") {
    return (
      <ul key={key} className="list-disc pl-6 space-y-1 my-2">
        {b.items.map((it, j) => (
          <li key={j} className="text-sm text-slate-800">{renderInline(it)}</li>
        ))}
      </ul>
    );
  }
  if (b.type === "paragraph") {
    return (
      <p key={key} className="text-sm leading-relaxed text-slate-800 my-2">
        {renderInline(b.text)}
      </p>
    );
  }
  if (b.type === "hr") {
    return <hr key={key} className="my-4 border-slate-200" />;
  }
  if (b.type === "raw") {
    return (
      <pre key={key} className="whitespace-pre-wrap rounded-lg bg-slate-100 p-3 text-xs font-mono my-3 overflow-x-auto">
        {b.text}
      </pre>
    );
  }
  return null;
}

export default function ProfileArtifact(props) {
  const seed = props.seed || SEED_PROFILE;
  const [content, setContent] = useState(seed);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [phase, setPhase] = useState("loading"); // loading | viewing | editing | saving
  const [draft, setDraft] = useState("");
  const [storageWarning, setStorageWarning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await safeGet(STORAGE_KEY);
      if (cancelled) return;
      if (stored && typeof stored.content === "string") {
        setContent(stored.content);
        setUpdatedAt(stored.updated_at || null);
      } else if (props.storageEnabled !== false) {
        // Bootstrap: seed empty profile so the skill side has something
        // to read on first run.
        const ok = await safeSet(STORAGE_KEY, {
          version: STORAGE_VERSION,
          content: seed,
          updated_at: new Date().toISOString(),
        });
        if (!ok) setStorageWarning(true);
        const verify = await safeGet(STORAGE_KEY);
        if (!verify && props.storageEnabled !== false) setStorageWarning(true);
      }
      setPhase("viewing");
    })();
    return () => { cancelled = true; };
  }, []);

  function startEdit() {
    setDraft(content);
    setPhase("editing");
  }

  function cancelEdit() {
    setDraft("");
    setPhase("viewing");
  }

  async function saveEdit() {
    setPhase("saving");
    const now = new Date().toISOString();
    const ok = await safeSet(STORAGE_KEY, {
      version: STORAGE_VERSION,
      content: draft,
      updated_at: now,
    });
    if (!ok) setStorageWarning(true);
    const verify = await safeGet(STORAGE_KEY);
    if (!verify) setStorageWarning(true);
    setContent(draft);
    setUpdatedAt(now);
    setPhase("viewing");
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-3xl px-4 pb-12 pt-6">
        <header className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h1 className="text-xl font-semibold">Reader profile</h1>
            <p className="text-xs text-slate-500">
              Living taste profile. The librarian writes here as you converse;
              you can edit it directly with the button on the right.
              {updatedAt && <> Last updated {fmtTs(updatedAt)}.</>}
            </p>
          </div>
          {phase === "viewing" && (
            <button
              type="button"
              onClick={startEdit}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-100"
            >
              Edit
            </button>
          )}
        </header>

        {storageWarning && <StorageWarning />}

        {phase === "editing" || phase === "saving" ? (
          <div className="space-y-3">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="w-full min-h-[60vh] rounded-xl border border-slate-300 bg-white p-3 font-mono text-sm leading-relaxed focus:border-emerald-500 focus:outline-none"
              spellCheck={false}
              disabled={phase === "saving"}
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelEdit}
                disabled={phase === "saving"}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveEdit}
                disabled={phase === "saving"}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:bg-slate-300"
              >
                {phase === "saving" ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        ) : (
          <article className="rounded-2xl bg-white p-6 ring-1 ring-slate-200">
            <MarkdownView source={content} />
          </article>
        )}
      </div>
    </div>
  );
}

function StorageWarning() {
  return (
    <div className="mb-4 rounded-2xl bg-amber-50 p-4 ring-1 ring-amber-200">
      <p className="text-sm font-medium text-amber-900">
        Heads up — profile changes may not be saving.
      </p>
      <p className="mt-1 text-sm text-amber-800">
        This artifact has to be published for storage to work. Click the
        Publish button on the artifact panel, then refresh.
      </p>
    </div>
  );
}

function fmtTs(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
