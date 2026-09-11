import { useEffect, useState } from "react";
import client, { apiErrorMessage } from "../api/client";
import { Button } from "./ui";

// Fetches a document's /preview endpoint as a blob (it requires the auth
// header, so a plain <iframe src="..."> pointed at the API can't be used)
// and renders it inline. Mime type is read from the response itself
// (blob.type) rather than trusted from the `document` prop, since not
// every place this is used carries a mime_type field on the row it's
// passed (e.g. EmployeeReviewSummary's /employees/{id} `documents` list
// doesn't include one).
export default function DocumentPreviewModal({ episodeId, document, onClose }) {
  const [objectUrl, setObjectUrl] = useState(null);
  const [mimeType, setMimeType] = useState(document?.mime_type || "");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let url = null;
    setLoading(true);
    setError("");
    setObjectUrl(null);
    client.get(`/employees/${episodeId}/documents/${document.id}/preview`, { responseType: "blob" })
      .then((res) => {
        url = URL.createObjectURL(res.data);
        setObjectUrl(url);
        setMimeType(res.data.type || document?.mime_type || "");
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));

    return () => {
      if (url) URL.revokeObjectURL(url);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [episodeId, document?.id]);

  async function download() {
    const res = await client.get(`/employees/${episodeId}/documents/${document.id}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = window.document.createElement("a");
    a.href = url;
    a.download = document.file_name || "document";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-5 w-full max-w-3xl max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-ink">{document.file_name || document.document_type || "Document Preview"}</h3>
          <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
        </div>

        {loading && <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>}
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

        {!loading && !error && objectUrl && (
          mimeType.startsWith("image/") ? (
            <img src={objectUrl} alt={document.file_name || "Document"} className="max-w-full max-h-[70vh] mx-auto" />
          ) : mimeType === "application/pdf" ? (
            <iframe src={objectUrl} title={document.file_name || "Document"} className="w-full h-[70vh]" />
          ) : (
            <div className="text-center py-10 space-y-3">
              <p className="text-sm text-ink/50">Preview not available for this file type.</p>
              <Button variant="outline" onClick={download}>Download</Button>
            </div>
          )
        )}
      </div>
    </div>
  );
}
