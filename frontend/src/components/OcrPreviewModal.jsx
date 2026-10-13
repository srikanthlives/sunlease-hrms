import { useEffect, useState } from "react";
import { Button, Input } from "./ui";

// Field labels/order per document kind - mirrors backend/app/services/
// ocr_service.py's returned field keys exactly, so no translation layer
// is needed between what the backend extracts and what this shows.
const FIELD_CONFIG = {
  AADHAAR: [
    ["aadhaar_name", "Name (as on Aadhaar)", "text"],
    ["aadhaar_dob", "Date of Birth (as on Aadhaar)", "date"],
    ["aadhaar", "Aadhaar Number", "text"],
    ["present_line1", "Address Line 1 (on Aadhaar)", "text"],
    ["present_city", "City", "text"],
    ["present_state", "State", "text"],
    ["present_pincode", "Pincode", "text"],
    ["present_country", "Country", "text"],
  ],
  PAN: [
    ["pan_name", "Name (as on PAN)", "text"],
    ["pan", "PAN Number", "text"],
    ["pan_dob", "Date of Birth (as on PAN)", "date"],
  ],
  DRIVING_LICENCE: [
    ["dl_licence_number", "Licence Number", "text"],
    ["dl_badge_number", "Badge Number", "text"],
    ["dl_vehicle_class", "Vehicle Class", "text"],
    ["dl_issuing_authority", "Issuing Authority", "text"],
    ["dl_issue_date", "HMV Issue Date", "date"],
    ["dl_expiry_date", "Expiry Date", "date"],
  ],
};

// Review-before-apply popup for OCR-extracted Aadhaar/PAN/Driving Licence
// fields (see services/ocr_service.py) - nothing is saved by this modal
// itself; Apply just hands the (possibly hand-corrected) values back to
// the caller, which merges them into whatever form already holds these
// fields (CandidateDetail's edit form / EmployeeWizard's step state) -
// the existing Save button there is what actually persists them. OCR
// over a phone photo of a government ID is never 100% - every field
// stays editable here before it goes anywhere.
export default function OcrPreviewModal({ title, loading, error, kind, fields, onApply, onClose }) {
  const [edited, setEdited] = useState(fields || {});

  useEffect(() => {
    setEdited(fields || {});
  }, [fields]);

  const config = FIELD_CONFIG[kind] || [];
  const nothingFound = !loading && !error && config.every(([key]) => !edited[key]);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-ink">{title || "Extracted Details"}</h3>
          <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
        </div>
        <p className="text-xs text-ink/40 mb-4">
          Read from the uploaded scan via OCR - review and correct anything before applying.
        </p>

        {loading && <div className="text-sm text-ink/40 py-10 text-center">Reading document…</div>}
        {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

        {!loading && !error && (
          <>
            {nothingFound && (
              <p className="text-sm text-ink/50 bg-ink/5 rounded-md px-3 py-2 mb-3">
                Couldn't confidently read any fields from this scan - try a clearer, well-lit photo, or enter the details manually.
              </p>
            )}
            <div className="space-y-2.5 max-h-[60vh] overflow-y-auto">
              {config.map(([key, label, type]) => (
                <Input
                  key={key} type={type} label={label} value={edited[key] || ""}
                  onChange={(e) => setEdited({ ...edited, [key]: e.target.value })}
                />
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button onClick={() => onApply(edited)}>Apply to Form</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
