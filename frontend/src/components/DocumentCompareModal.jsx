import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Button } from "./ui";

// One side of the comparison: fetches its own file as a blob (auth header
// required, same reasoning as DocumentPreviewModal) and renders it inline.
function PreviewPane({ label, fileName, url }) {
  const [objectUrl, setObjectUrl] = useState(null);
  const [mimeType, setMimeType] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let created = null;
    setLoading(true);
    setError("");
    setObjectUrl(null);
    client.get(url, { responseType: "blob" })
      .then((res) => {
        created = URL.createObjectURL(res.data);
        setObjectUrl(created);
        setMimeType(res.data.type || "");
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
    return () => { if (created) URL.revokeObjectURL(created); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  async function download() {
    const res = await client.get(url, { responseType: "blob" });
    const blobUrl = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = fileName || "document";
    a.click();
    URL.revokeObjectURL(blobUrl);
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col border border-ink/10 rounded-md overflow-hidden">
      <div className="px-3 py-2 border-b border-ink/10 bg-ink/[0.02] shrink-0">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-ink/40">{label}</div>
        <div className="text-xs text-ink/70 truncate" title={fileName}>{fileName || "—"}</div>
      </div>
      <div className="flex-1 min-h-0 overflow-auto flex items-center justify-center p-2">
        {loading && <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>}
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 m-2">{error}</div>}
        {!loading && !error && objectUrl && (
          mimeType.startsWith("image/") ? (
            <img src={objectUrl} alt={fileName || label} className="max-w-full max-h-full mx-auto" />
          ) : mimeType === "application/pdf" ? (
            <iframe src={objectUrl} title={fileName || label} className="w-full h-full" />
          ) : (
            <div className="text-center py-10 space-y-3">
              <p className="text-sm text-ink/50">Preview not available for this file type.</p>
              <Button variant="outline" size="sm" onClick={download}>Download</Button>
            </div>
          )
        )}
      </div>
    </div>
  );
}

// Side-by-side comparison of an "old" (currently live) and "new" (staged,
// pending approval) file for a document-replacement change request - so a
// reviewer can see exactly what's being swapped before approving it.
export default function DocumentCompareModal({ title, oldUrl, oldFileName, newUrl, newFileName, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-5 w-full max-w-[95vw] h-[95vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4 shrink-0">
          <h3 className="text-sm font-semibold text-ink">{title || "Compare Documents"}</h3>
          <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
        </div>
        <div className="flex-1 min-h-0 flex flex-col md:flex-row gap-4">
          <PreviewPane label="Current (before)" fileName={oldFileName} url={oldUrl} />
          <PreviewPane label="Proposed (after)" fileName={newFileName} url={newUrl} />
        </div>
      </div>
    </div>
  );
}
