"use client";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowDownToLine } from "lucide-react";

export default function DocsPanel({ docs, name }: { docs: { brd_md: string; prd_md: string }; name: string }) {
  const [tab, setTab] = useState<"brd" | "prd">("brd");
  const md = tab === "brd" ? docs.brd_md : docs.prd_md;
  const download = () => {
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${tab}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section className="app-card docs-section">
      <div className="docs-head">
        <div>
          <span className="mini-label">THE ARCHITECT</span>
          <h2>
            Your BRD and PRD, <em>written from the crowd.</em>
          </h2>
        </div>
        <div className="chip-row" role="tablist" aria-label="Document">
          {(["brd", "prd"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={`chip ${tab === t ? "on" : ""}`}
              onClick={() => setTab(t)}
            >
              {t.toUpperCase()}
            </button>
          ))}
          <button className="chip" onClick={download}>
            <ArrowDownToLine size={14} /> Markdown
          </button>
        </div>
      </div>
      <article className="doc-paper" role="tabpanel">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
      </article>
    </section>
  );
}
