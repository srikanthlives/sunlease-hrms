import { useEffect, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Download, FileWarning, X } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Button } from "./ui";

/**
 * Bulk document download, shared by the Employees and Candidates lists.
 *
 * Opens on a selection of people, asks the backend which document types any
 * of them actually have on file, and lets you tick several. Each person then
 * comes back as ONE merged PDF containing the ticked documents in the order
 * shown; several people arrive as a .zip of one PDF each, a single person as
 * a bare PDF.
 *
 * The type list is deliberately the types these people HAVE, not the whole
 * Document Configuration master - a tick box for something nobody uploaded
 * is a guaranteed line in the skipped report.
 *
 * Props: entity ("EMPLOYEE" | "CANDIDATE"), ids (number[]), onClose, onDone
 */
export default function DocumentBundleModal({ entity, ids, onClose, onDone }) {
  const [info, setInfo] = useState(null);     // { people, document_types, people_with_no_documents, pdf_merge_available }
  const [picked, setPicked] = useState([]);   // ordered document_type_ids - this order is the page order
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  const label = entity === "EMPLOYEE" ? "employee" : "candidate";

  useEffect(() => {
    let live = true;
    client.post("/exports/documents/preflight", { entity, ids })
      .then((res) => {
        if (!live) return;
        setInfo(res.data);
        // Pre-tick the types everyone in the selection has - the common case
        // is "give me the complete file for these people".
        setPicked(res.data.document_types.filter((t) => t.missing_count === 0).map((t) => t.document_type_id));
      })
      .catch((err) => live && setLoadError(apiErrorMessage(err)));
    return () => { live = false; };
  }, [entity, ids.join(",")]);

  function toggle(id) {
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function move(id, delta) {
    setPicked((prev) => {
      const from = prev.indexOf(id);
      const to = from + delta;
      if (from < 0 || to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      next.splice(to, 0, next.splice(from, 1)[0]);
      return next;
    });
  }

  async function download() {
    setBusy(true);
    setError("");
    try {
      const res = await client.post(
        "/exports/documents/download",
        { entity, ids, document_type_ids: picked },
        { responseType: "blob" },
      );
      const disposition = res.headers["content-disposition"] || "";
      const match = /filename="?([^"]+)"?/.exec(disposition);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = match ? match[1] : `hrms_${label}_documents.zip`;
      a.click();
      URL.revokeObjectURL(url);
      onDone?.({
        people: Number(res.headers["x-bundle-people"] || 0),
        documents: Number(res.headers["x-bundle-documents"] || 0),
        skipped: Number(res.headers["x-bundle-skipped"] || 0),
      });
      onClose();
    } catch (err) {
      // A failed download arrives as a blob too, so the JSON detail inside
      // it has to be read out before it can be shown.
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          setError(JSON.parse(text).detail || text);
        } catch {
          setError(apiErrorMessage(err));
        }
      } else {
        setError(apiErrorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  const byId = Object.fromEntries((info?.document_types || []).map((t) => [t.document_type_id, t]));
  const peopleCount = info?.people?.length ?? ids.length;
  // How many documents would actually be in the file, and how many ticked
  // boxes have no file behind them for someone.
  const willInclude = picked.reduce((sum, id) => sum + (byId[id]?.uploaded_count || 0), 0);
  const willSkip = picked.reduce((sum, id) => sum + (byId[id]?.missing_count || 0), 0);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => !busy && onClose()}>
      <div className="bg-white rounded-lg w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-ink/10 px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">
              Download Documents — {peopleCount} {label}{peopleCount === 1 ? "" : "s"}
            </h3>
            <p className="text-xs text-ink/50 mt-0.5">
              Each {label} comes back as one PDF with the ticked documents as pages, in the order below.
              {peopleCount > 1 && " Several people arrive as a .zip of one PDF each."}
            </p>
          </div>
          <button className="text-ink/40 hover:text-ink" onClick={onClose} title="Close"><X size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loadError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{loadError}</div>}
          {!info && !loadError && <div className="text-sm text-ink/40 py-8 text-center">Checking what's on file…</div>}

          {info && info.document_types.length === 0 && (
            <div className="text-sm text-ink/60 bg-ink/[0.03] rounded-md px-3 py-3">
              None of the selected {label}s have any documents uploaded, so there is nothing to download.
            </div>
          )}

          {info && info.document_types.length > 0 && (
            <>
              <div className="text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">
                Documents on file for this selection
              </div>
              <div className="space-y-0.5">
                {info.document_types.map((type) => (
                  <label
                    key={type.document_type_id}
                    className="flex items-center gap-2 text-sm text-ink/80 cursor-pointer hover:bg-ink/[0.02] rounded px-1.5 py-1"
                  >
                    <input
                      type="checkbox" className="rounded border-ink/30"
                      checked={picked.includes(type.document_type_id)}
                      onChange={() => toggle(type.document_type_id)}
                    />
                    <span className="flex-1">{type.name}</span>
                    <span className={`text-xs ${type.missing_count === 0 ? "text-ink/40" : "text-accent-600"}`}>
                      {type.uploaded_count} of {type.uploaded_count + type.missing_count}
                      {type.missing_count > 0 && ` · ${type.missing_count} missing`}
                    </span>
                  </label>
                ))}
              </div>
              <div className="mt-1.5 flex gap-2">
                <button className="text-xs text-brand-600 hover:underline"
                  onClick={() => setPicked(info.document_types.map((t) => t.document_type_id))}>
                  Select all
                </button>
                <button className="text-xs text-brand-600 hover:underline" onClick={() => setPicked([])}>
                  Clear
                </button>
              </div>

              {picked.length > 0 && (
                <>
                  <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-ink/40 mb-2">
                    Page order in each PDF
                  </div>
                  <ol className="space-y-0.5">
                    {picked.map((id, index) => (
                      <li key={id} className="flex items-center gap-1.5 text-xs rounded border border-ink/10 px-2 py-1">
                        <span className="w-5 text-ink/35 tabular-nums">{index + 1}</span>
                        <span className="flex-1 truncate text-ink/80">{byId[id]?.name || id}</span>
                        <button className="text-ink/30 hover:text-brand-600 disabled:opacity-20" disabled={index === 0}
                          onClick={() => move(id, -1)} title="Move up"><ArrowUp size={13} /></button>
                        <button className="text-ink/30 hover:text-brand-600 disabled:opacity-20" disabled={index === picked.length - 1}
                          onClick={() => move(id, 1)} title="Move down"><ArrowDown size={13} /></button>
                        <button className="text-ink/30 hover:text-danger" onClick={() => toggle(id)} title="Remove">
                          <X size={13} />
                        </button>
                      </li>
                    ))}
                  </ol>
                  <p className="mt-2 text-xs text-ink/60">
                    <strong>{willInclude}</strong> document{willInclude === 1 ? "" : "s"} will be included
                    {willSkip > 0 && (
                      <> · <strong>{willSkip}</strong> ticked document{willSkip === 1 ? " is" : "s are"} not uploaded for
                      someone in this selection and will be listed in a <code>_skipped.txt</code> inside the download</>
                    )}
                  </p>
                </>
              )}

              {info.people_with_no_documents.length > 0 && (
                <div className="mt-3 flex gap-2 text-xs text-ink/60 bg-ink/[0.03] rounded-md px-3 py-2">
                  <FileWarning size={14} className="shrink-0 mt-0.5 text-accent-600" />
                  <span>
                    {info.people_with_no_documents.length} selected {label}
                    {info.people_with_no_documents.length === 1 ? " has" : "s have"} no documents at all and
                    will produce no PDF: {info.people_with_no_documents.slice(0, 6).join(", ")}
                    {info.people_with_no_documents.length > 6 && ` and ${info.people_with_no_documents.length - 6} more`}
                  </span>
                </div>
              )}

              {!info.pdf_merge_available && (
                <div className="mt-3 flex gap-2 text-xs text-ink/70 bg-accent-50 border border-accent-600/20 rounded-md px-3 py-2">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5 text-accent-600" />
                  <span>
                    PDF merging is unavailable on this server (the <code>pypdf</code> package is not installed),
                    so any document that was uploaded as a PDF will be listed as skipped instead of merged.
                    Documents uploaded as images are unaffected.
                  </span>
                </div>
              )}
            </>
          )}

          {error && <div className="mt-3 text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}
        </div>

        <div className="flex items-center gap-2 border-t border-ink/10 px-5 py-3">
          <span className="ml-auto flex gap-2">
            <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button onClick={download} disabled={busy || picked.length === 0 || willInclude === 0} className="gap-1.5">
              <Download size={14} /> {busy ? "Preparing…" : peopleCount > 1 ? "Download .zip" : "Download .pdf"}
            </Button>
          </span>
        </div>
      </div>
    </div>
  );
}
