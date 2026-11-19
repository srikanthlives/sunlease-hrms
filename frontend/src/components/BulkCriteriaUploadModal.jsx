import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Ban, FileText, Upload, X } from "lucide-react";
import client, { apiErrorMessage } from "../api/client";
import { Button, Select } from "./ui";

/**
 * Bulk proof upload for a selection criteria, from the Candidates list.
 *
 * One test, one report sheet, many candidates - e.g. a training whose single
 * assessment report lists all 20 attendees. The file is uploaded and stored
 * ONCE on the server and every selected candidate's stage result points at
 * that same copy.
 *
 * It files the PROOF only. PASS/FAIL stays a per-candidate decision made on
 * each candidate's own page, precisely because such a report normally
 * carries both - marking twenty people PASS because one document covers them
 * is the mistake this is meant to avoid, not a shortcut it should take.
 *
 * Only criteria configured with "Supports bulk upload" are offered, and only
 * candidates whose designation actually requires the chosen test can take
 * it - the rest are shown greyed out with the reason rather than silently
 * dropped.
 *
 * Props: ids (candidate ids), onClose, onDone
 */
export default function BulkCriteriaUploadModal({ ids, onClose, onDone }) {
  const [criteria, setCriteria] = useState(null);     // bulk-capable criteria list
  const [criteriaId, setCriteriaId] = useState("");
  const [preflight, setPreflight] = useState(null);   // { criteria, candidates: [...] }
  const [checking, setChecking] = useState(false);
  const [excluded, setExcluded] = useState([]);       // candidate ids HR chose to leave out
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const fileRef = useRef(null);

  useEffect(() => {
    let live = true;
    client.get("/recruitment/bulk-criteria")
      .then((res) => {
        if (!live) return;
        setCriteria(res.data);
        if (res.data.length === 1) setCriteriaId(String(res.data[0].id));
      })
      .catch((err) => live && setLoadError(apiErrorMessage(err)));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!criteriaId) { setPreflight(null); return; }
    let live = true;
    setChecking(true);
    setError("");
    client.get("/recruitment/bulk-criteria-preflight", {
      params: { criteria_id: criteriaId, candidate_ids: ids.join(",") },
    })
      .then((res) => {
        if (!live) return;
        setPreflight(res.data);
        // Candidates who already have a result recorded start EXCLUDED - an
        // existing result is evidence someone already dealt with this
        // person, so including them is a deliberate act, not the default.
        setExcluded(res.data.candidates.filter((c) => c.existing_result).map((c) => c.candidate_id));
      })
      .catch((err) => live && setError(apiErrorMessage(err)))
      .finally(() => live && setChecking(false));
    return () => { live = false; };
  }, [criteriaId, ids.join(",")]);

  const rows = preflight?.candidates || [];
  const eligible = rows.filter((r) => !r.blocked_reason);
  const blocked = rows.filter((r) => r.blocked_reason);
  const included = eligible.filter((r) => !excluded.includes(r.candidate_id));

  function toggle(candidateId) {
    setExcluded((prev) => (prev.includes(candidateId) ? prev.filter((x) => x !== candidateId) : [...prev, candidateId]));
  }

  async function upload() {
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("criteria_id", criteriaId);
      form.append("candidate_ids", included.map((r) => r.candidate_id).join(","));
      form.append("file", file);
      const res = await client.post("/recruitment/candidates-bulk-stage-attachment", form);
      onDone?.({ ...res.data, criteria_name: preflight?.criteria?.name });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => !busy && onClose()}>
      <div className="bg-white rounded-lg w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-ink/10 px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">
              Upload Test Document — {ids.length} candidate{ids.length === 1 ? "" : "s"}
            </h3>
            <p className="text-xs text-ink/50 mt-0.5">
              One report covering several candidates. The file is stored once and shared by everyone included below.
              PASS/FAIL is still recorded on each candidate individually.
            </p>
          </div>
          <button className="text-ink/40 hover:text-ink" onClick={onClose} title="Close"><X size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {loadError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{loadError}</div>}
          {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

          {criteria && criteria.length === 0 && (
            <div className="text-sm text-ink/60 bg-ink/[0.03] rounded-md px-3 py-3">
              No selection criteria are configured for bulk upload yet. Tick <strong>Supports bulk upload</strong> on a
              criteria under Administration &gt; Selection Criteria first.
            </div>
          )}

          {criteria && criteria.length > 0 && (
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink/40 mb-1">Test / Criteria</label>
              <Select value={criteriaId} onChange={(e) => setCriteriaId(e.target.value)}>
                <option value="">Select a test…</option>
                {criteria.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </div>
          )}

          {checking && <div className="text-sm text-ink/40 py-6 text-center">Checking the selected candidates…</div>}

          {!checking && preflight && (
            <>
              <div className="text-xs font-semibold uppercase tracking-wide text-ink/40">
                Candidates — {included.length} of {rows.length} will get this document
              </div>
              <div className="space-y-0.5">
                {eligible.map((r) => (
                  <label key={r.candidate_id}
                    className="flex items-center gap-2 text-sm text-ink/80 cursor-pointer hover:bg-ink/[0.02] rounded px-1.5 py-1">
                    <input type="checkbox" className="rounded border-ink/30"
                      checked={!excluded.includes(r.candidate_id)} onChange={() => toggle(r.candidate_id)} />
                    <span className="flex-1 truncate">
                      {r.name}
                      <span className="text-ink/40 text-xs ml-1.5">{r.reference_number}</span>
                    </span>
                    {r.existing_result && (
                      <span className="text-xs text-accent-600 shrink-0">
                        already recorded · {r.existing_result}
                        {r.existing_attachment && " · has a document"}
                      </span>
                    )}
                  </label>
                ))}
                {blocked.map((r) => (
                  <div key={r.candidate_id}
                    className="flex items-center gap-2 text-sm text-ink/35 rounded px-1.5 py-1" title={r.blocked_reason}>
                    <Ban size={14} className="shrink-0" />
                    <span className="flex-1 truncate">
                      {r.name}
                      <span className="text-xs ml-1.5">{r.reference_number}</span>
                    </span>
                    <span className="text-xs shrink-0 truncate max-w-[18rem]">{r.blocked_reason}</span>
                  </div>
                ))}
              </div>
              {blocked.length > 0 && (
                <div className="flex gap-2 text-xs text-ink/60 bg-ink/[0.03] rounded-md px-3 py-2">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5 text-accent-600" />
                  <span>
                    {blocked.length} selected candidate{blocked.length === 1 ? " cannot" : "s cannot"} take this
                    document and {blocked.length === 1 ? "is" : "are"} left out. Deselect {blocked.length === 1 ? "them" : "them"} on
                    the list, or pick a different test.
                  </span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink/40 mb-1">Report document</label>
                <input ref={fileRef} type="file" className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)} />
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
                    <Upload size={14} className="mr-1.5" />{file ? "Change file" : "Choose file"}
                  </Button>
                  {file
                    ? <span className="text-sm text-ink/70 flex items-center gap-1.5 truncate">
                        <FileText size={14} className="shrink-0 text-ink/40" />{file.name}
                      </span>
                    : <span className="text-sm text-ink/40">No file chosen</span>}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-ink/10 px-5 py-3">
          <span className="text-xs text-ink/50">
            {included.length > 0 && file
              ? `One copy stored, shared by ${included.length} candidate${included.length === 1 ? "" : "s"}`
              : "Pick a test, the candidates to include, and the report file"}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button size="sm" onClick={upload} disabled={busy || !file || included.length === 0}>
              {busy ? "Uploading…" : `Upload for ${included.length}`}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
