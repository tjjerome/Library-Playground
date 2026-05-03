// Library-Playground profile artifact — claude.ai port.
//
// Pure read-only renderer for the reader's `Profile.md` content.
// Skills pass content via the `seed` prop (markdown text).  No
// window.storage, no persistence, no preflight.  The source of truth
// for Profile.md lives in /mnt/project/Profile.md (uploaded to project
// knowledge by the reader); the librarian's in-session edits land in
// /tmp/Profile.md and surface at session end via present_files for the
// reader to download and re-upload.

import React, { useMemo } from "react";

const SEED_PROFILE = `# Reader Profile

_Living memory — updated throughout reading-list builds._
`;

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

function MarkdownView({ source }) {
  const blocks = useMemo(() => parseMarkdown(source || ""), [source]);
  return (
    <div className="prose prose-slate max-w-none">
      {blocks.map((b, i) => renderBlock(b, i))}
    </div>
  );
}

export default function ProfileArtifact(props) {
  const content = props.seed || SEED_PROFILE;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-3xl px-4 pb-12 pt-6">
        <header className="mb-4">
          <h1 className="text-xl font-semibold">Reader profile</h1>
          <p className="text-xs text-slate-500">
            Read-only preview of your taste profile.  To edit, tell the
            librarian in chat — at session end you'll get a download
            link to replace your project-knowledge `Profile.md`.
          </p>
        </header>

        <article className="rounded-2xl bg-white p-6 ring-1 ring-slate-200">
          <MarkdownView source={content} />
        </article>
      </div>
    </div>
  );
}
