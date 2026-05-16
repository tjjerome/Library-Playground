// Library-Playground reading-list artifact — claude.ai port.
//
// Pure read-only renderer for the reader's `Reading_List.md` content.
// Skills pass content via the `seed` prop (markdown text).  No
// window.storage, no persistence, no preflight.  The source of truth
// for Reading_List.md lives in /mnt/project/Reading_List.md (uploaded
// to project knowledge by the reader); the librarian's in-session
// edits land in /tmp/Reading_List.md and surface at session end via
// present_files for the reader to download and re-upload.

import React, { useMemo, useState } from "react";

const SEED = `# Reading List

_The librarian builds this list as you converse.  Every entry was a
deliberate pick from a batch — the order doesn't imply reading order,
it's a TBR pool you can browse by mood.  To remove or swap, tell the
librarian in chat._
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
    } else if (/^\s*\|/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        rows.push(lines[i]);
        i++;
      }
      blocks.push({ type: "table", rows: parseTable(rows) });
    } else if (/^\s*[-*]\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push({ type: "bullets", items });
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

function parseTable(rows) {
  const cells = rows.map((row) =>
    row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim())
  );
  return cells.filter((cells) => !cells.every((c) => /^[-:\s]+$/.test(c)));
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
    const em = rest.match(/^\*([^*]+)\*/) || rest.match(/^_([^_]+)_/);
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
        ? "text-lg font-semibold mt-6 mb-3 border-b border-slate-200 pb-1"
        : "text-base font-semibold mt-4 mb-2";
    return <Tag key={key} className={cls}>{renderInline(b.text)}</Tag>;
  }
  if (b.type === "paragraph") {
    return (
      <p key={key} className="text-sm leading-relaxed text-slate-700 my-2">
        {renderInline(b.text)}
      </p>
    );
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
  if (b.type === "hr") {
    return <hr key={key} className="my-4 border-slate-200" />;
  }
  if (b.type === "table") {
    if (b.rows.length === 0) return null;
    const [header, ...body] = b.rows;
    return (
      <div key={key} className="my-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="bg-slate-100">
            <tr>
              {header.map((h, j) => (
                <th key={j} className="border border-slate-200 px-3 py-2 text-left font-semibold text-slate-700">
                  {renderInline(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                {row.map((cell, j) => (
                  <td key={j} className="border border-slate-200 px-3 py-2 text-slate-800 align-top">
                    {renderInline(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return null;
}

function MarkdownView({ source }) {
  const blocks = useMemo(() => parseMarkdown(source || ""), [source]);
  return <div>{blocks.map((b, i) => renderBlock(b, i))}</div>;
}

export default function ReadingListArtifact(props) {
  const content = props.seed || SEED;
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-4xl px-4 pb-12 pt-6">
        <header className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h1 className="text-xl font-semibold">Reading list</h1>
            <p className="text-xs text-slate-500">
              Read-only preview of your reading list.  Built and edited by
              the librarian as you converse — at session end you'll get
              a download link to replace your project-knowledge
              `Reading_List.md`.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowRaw(!showRaw)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-100"
          >
            {showRaw ? "View rendered" : "View raw"}
          </button>
        </header>

        <article className="rounded-2xl bg-white p-6 ring-1 ring-slate-200">
          {showRaw ? (
            <pre className="whitespace-pre-wrap font-mono text-xs text-slate-800">
              {content}
            </pre>
          ) : (
            <MarkdownView source={content} />
          )}
        </article>
      </div>
    </div>
  );
}
