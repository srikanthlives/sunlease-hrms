import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Checkbox, SectionDivider, StatusBadge, formatDate } from "../components/ui";

// Driving Licence is inserted before Review & Submit only when a
// DrivingLicenceRequirement rule matches this employee's Employee Type/
// Category/Designation (see licence_service.py on the backend) - the
// base list stays fixed at indices 0-7 either way.
const BASE_STEPS = [
  "Personal Information",
  "Address",
  "Employment Information",
  "Organizational Assignment",
  "Statutory Information",
  "Bank Information",
  "Documents",
  "Dependents / Nominees",
];

// Mirrors backend/app/core/validators.py - kept in sync manually since
// the frontend and backend don't share a validation layer. Only checked
// when the field is non-empty (all three are optional).
const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
const AADHAAR_REGEX = /^[2-9][0-9]{11}$/;
const IFSC_REGEX = /^[A-Z]{4}0[A-Z0-9]{6}$/;
const MOBILE_REGEX = /^[6-9][0-9]{9}$/;
const PINCODE_REGEX = /^[0-9]{6}$/;
const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function formatError(value, regex, message) {
  return value && !regex.test(value) ? message : undefined;
}

const emptyAddress = {
  present_line1: "", present_line2: "", present_city: "", present_state: "", present_pincode: "", present_country: "",
  same_as_present: false,
  permanent_line1: "", permanent_line2: "", permanent_city: "", permanent_state: "", permanent_pincode: "", permanent_country: "",
};

export default function EmployeeWizard() {
  const { episodeId } = useParams();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);
  const [masters, setMasters] = useState({ costCenters: [], departments: [], projects: [], categories: [], workLocations: [], designations: [], employeeTypes: [] });

  const [personal, setPersonal] = useState({});
  const [address, setAddress] = useState(emptyAddress);
  const [employment, setEmployment] = useState({});
  const [assignment, setAssignment] = useState({ effective_from: "" });
  const [allocation, setAllocation] = useState({ cost_center_id: "", project_id: "", percentage: "", effective_from: "" });
  const [allocationBusy, setAllocationBusy] = useState(false);
  const [allocationError, setAllocationError] = useState("");
  const [statutory, setStatutory] = useState({});
  const [bank, setBank] = useState({ effective_from: "" });
  const [dependent, setDependent] = useState({ name: "" });
  const [dependentBusy, setDependentBusy] = useState(false);
  const [dependentError, setDependentError] = useState("");
  const [nominee, setNominee] = useState({ name: "" });
  const [nomineeBusy, setNomineeBusy] = useState(false);
  const [nomineeError, setNomineeError] = useState("");
  const [requiredDocs, setRequiredDocs] = useState([]);
  const [docUploadingId, setDocUploadingId] = useState(null);
  const [docError, setDocError] = useState("");
  const [dlRequirement, setDlRequirement] = useState({ show: false, is_required: false });
  const [drivingLicence, setDrivingLicence] = useState({});
  const [photoUrl, setPhotoUrl] = useState(null);
  const [photoUploading, setPhotoUploading] = useState(false);

  const steps = dlRequirement.show ? [...BASE_STEPS, "Driving Licence", "Review & Submit"] : [...BASE_STEPS, "Review & Submit"];
  const STEP_DRIVING_LICENCE = dlRequirement.show ? BASE_STEPS.length : -1;
  const STEP_REVIEW = steps.length - 1;

  function loadDetail() {
    client.get(`/employees/${episodeId}`).then((res) => {
      setDetail(res.data);
      setPersonal(res.data.employee);
      setAddress({ ...emptyAddress, ...res.data.address });
      setEmployment(res.data.episode);
      setDrivingLicence(res.data.driving_licence || {});
      if (res.data.employee.has_photo) loadPhoto(); else setPhotoUrl(null);
    });
  }

  function loadPhoto() {
    client.get(`/employees/${episodeId}/photo`, { responseType: "blob" })
      .then((res) => setPhotoUrl(URL.createObjectURL(res.data)))
      .catch(() => setPhotoUrl(null));
  }

  async function uploadPhoto(file) {
    if (!file) return;
    setPhotoUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      await client.put(`/employees/${episodeId}/photo`, form);
      loadDetail();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setPhotoUploading(false);
    }
  }

  function loadRequiredDocs() {
    client.get(`/employees/${episodeId}/required-documents`).then((res) => setRequiredDocs(res.data));
  }

  function loadDrivingLicenceRequirement() {
    client.get(`/employees/${episodeId}/driving-licence-requirement`).then((res) => setDlRequirement(res.data));
  }

  useEffect(() => {
    loadDetail();
    loadDrivingLicenceRequirement();
    Promise.all([
      client.get("/cost-centers"),
      client.get("/departments"),
      client.get("/projects"),
      client.get("/employee-categories"),
      client.get("/work-locations"),
      client.get("/designations"),
      client.get("/employee-types"),
    ]).then(([cc, dept, proj, cat, wl, desig, etype]) => {
      setMasters({
        costCenters: cc.data, departments: dept.data, projects: proj.data, categories: cat.data,
        workLocations: wl.data, designations: desig.data, employeeTypes: etype.data,
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [episodeId]);

  useEffect(() => {
    if (step === 6) {
      loadRequiredDocs();
      loadDrivingLicenceRequirement();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, episodeId]);

  async function save(path, payload, method = "post") {
    setSaving(true);
    setError("");
    try {
      const res = await client[method](`/employees/${episodeId}${path}`, payload);
      loadDetail();
      if (res.data?.submitted_for_approval) {
        setBanner("Submitted for approval — this change won't take effect until an Approver reviews it (see Change Requests).");
      }
      return true;
    } catch (err) {
      setError(apiErrorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function addAllocation() {
    setAllocationBusy(true);
    setAllocationError("");
    try {
      await client.post(`/employees/${episodeId}/allocation`, {
        cost_center_id: Number(allocation.cost_center_id),
        project_id: allocation.project_id ? Number(allocation.project_id) : null,
        percentage: Number(allocation.percentage),
        effective_from: allocation.effective_from,
      });
      setAllocation({ cost_center_id: "", project_id: "", percentage: "", effective_from: allocation.effective_from });
      loadDetail();
    } catch (err) {
      setAllocationError(apiErrorMessage(err));
    } finally {
      setAllocationBusy(false);
    }
  }

  async function removeAllocation(allocationId) {
    setAllocationBusy(true);
    setAllocationError("");
    try {
      await client.delete(`/employees/${episodeId}/allocation/${allocationId}`);
      loadDetail();
    } catch (err) {
      setAllocationError(apiErrorMessage(err));
    } finally {
      setAllocationBusy(false);
    }
  }

  async function addDependent() {
    setDependentBusy(true);
    setDependentError("");
    try {
      await client.post(`/employees/${episodeId}/dependents`, dependent);
      setDependent({ name: "" });
      loadDetail();
    } catch (err) {
      setDependentError(apiErrorMessage(err));
    } finally {
      setDependentBusy(false);
    }
  }

  async function removeDependent(dependentId) {
    setDependentBusy(true);
    setDependentError("");
    try {
      await client.delete(`/employees/${episodeId}/dependents/${dependentId}`);
      loadDetail();
    } catch (err) {
      setDependentError(apiErrorMessage(err));
    } finally {
      setDependentBusy(false);
    }
  }

  async function addNominee() {
    setNomineeBusy(true);
    setNomineeError("");
    try {
      await client.post(`/employees/${episodeId}/nominees`, {
        ...nominee,
        percentage: nominee.percentage ? Number(nominee.percentage) : null,
      });
      setNominee({ name: "" });
      loadDetail();
    } catch (err) {
      setNomineeError(apiErrorMessage(err));
    } finally {
      setNomineeBusy(false);
    }
  }

  async function removeNominee(nomineeId) {
    setNomineeBusy(true);
    setNomineeError("");
    try {
      await client.delete(`/employees/${episodeId}/nominees/${nomineeId}`);
      loadDetail();
    } catch (err) {
      setNomineeError(apiErrorMessage(err));
    } finally {
      setNomineeBusy(false);
    }
  }

  async function uploadDocument(documentTypeId, file) {
    if (!file) return;
    setDocUploadingId(documentTypeId);
    setDocError("");
    try {
      const form = new FormData();
      form.append("document_type_id", documentTypeId);
      form.append("file", file);
      await client.post(`/employees/${episodeId}/documents`, form);
      loadRequiredDocs();
    } catch (err) {
      setDocError(apiErrorMessage(err));
    } finally {
      setDocUploadingId(null);
    }
  }

  async function removeDocument(documentMetaId) {
    setDocError("");
    try {
      await client.delete(`/employees/${episodeId}/documents/${documentMetaId}`);
      loadRequiredDocs();
    } catch (err) {
      setDocError(apiErrorMessage(err));
    }
  }

  async function downloadDocument(documentMetaId, fileName) {
    const res = await client.get(`/employees/${episodeId}/documents/${documentMetaId}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName || "document";
    a.click();
    URL.revokeObjectURL(url);
  }

  // Persists whatever's pending on the *current* step. Shared by
  // "Save & Continue" and by jumping directly to another step via the
  // step pills - without this, an edited-but-unsaved field (e.g. Employee
  // Category) would still be its old value server-side when a later step
  // (like Documents, which reads Category from the server to resolve
  // required documents) is opened directly instead of via Next.
  async function saveCurrentStep() {
    if (step === 0) {
      return save("/personal", {
        ...personal,
        total_experience_years: personal.total_experience_years === "" || personal.total_experience_years == null ? null : Number(personal.total_experience_years),
      }, "put");
    }
    if (step === 1) return save("/address", address, "put");
    if (step === 2) {
      const ok = await save("/employment", employment, "put");
      if (ok) loadDrivingLicenceRequirement();
      return ok;
    }
    if (step === 3 && assignment.effective_from) {
      return save("/assignment", {
        ...assignment,
        cost_center_id: Number(assignment.cost_center_id),
        department_id: Number(assignment.department_id),
        project_id: assignment.project_id ? Number(assignment.project_id) : null,
      });
      // Cost allocations are added individually via "Add Allocation" below
      // (each hits the API immediately) - not part of this step's save.
    }
    if (step === 4) return save("/statutory", statutory);
    if (step === 5 && bank.effective_from) return save("/bank", bank);
    // Dependents/Nominees are added individually via their own "Add"
    // buttons below (each hits the API immediately) - not part of this
    // step's save, same pattern as Cost Allocation.
    if (step === STEP_DRIVING_LICENCE) return save("/driving-licence", drivingLicence, "put");
    return true;
  }

  async function next() {
    const ok = await saveCurrentStep();
    if (ok && step < steps.length - 1) setStep(step + 1);
  }

  async function goToStep(index) {
    if (index === step) return;
    const ok = await saveCurrentStep();
    if (ok) setStep(index);
  }

  async function submit() {
    const ok = await save("/submit", {});
    if (ok) navigate(`/employees/${episodeId}`);
  }

  if (!detail) return <div className="text-sm text-ink/40 py-10 text-center">Loading…</div>;

  const allocationTotal = detail.allocations.filter((a) => !a.effective_to).reduce((sum, a) => sum + a.percentage, 0);
  const nomineeTotalForType = detail.nominees
    .filter((n) => (n.nomination_type || null) === (nominee.nomination_type || null))
    .reduce((sum, n) => sum + (n.percentage || 0), 0);

  const currentStepHasError = !!(
    (step === 0 && (
      formatError(personal.aadhaar, AADHAAR_REGEX, "x") || formatError(personal.pan, PAN_REGEX, "x") ||
      formatError(personal.mobile_number, MOBILE_REGEX, "x") || formatError(personal.alternate_mobile_number, MOBILE_REGEX, "x") ||
      formatError(personal.emergency_contact_mobile, MOBILE_REGEX, "x") ||
      formatError(personal.personal_email, EMAIL_REGEX, "x") || formatError(personal.official_email, EMAIL_REGEX, "x")
    )) ||
    (step === 1 && (formatError(address.present_pincode, PINCODE_REGEX, "x") || formatError(address.permanent_pincode, PINCODE_REGEX, "x"))) ||
    (step === 5 && formatError(bank.ifsc, IFSC_REGEX, "x"))
  );

  return (
    <div className="space-y-5">
      <div className="print:hidden">
        <h1 className="text-xl font-display font-semibold text-ink">New Employee — {steps[step]}</h1>
        <p className="text-sm text-ink/50 mt-1">Step {step + 1} of {steps.length} · saved as Draft after each step</p>
      </div>

      <div className="flex gap-1.5 flex-wrap print:hidden">
        {steps.map((s, i) => (
          <button
            key={s}
            onClick={() => goToStep(i)}
            className={`text-[11px] px-2.5 py-1 rounded-full border ${
              i === step ? "bg-brand-800 text-white border-brand-800" : "bg-white text-ink/50 border-ink/15"
            }`}
          >
            {i + 1}. {s}
          </button>
        ))}
      </div>

      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 print:hidden">{error}</div>}
      {banner && <div className="text-sm text-brand-800 bg-brand-50 rounded-md px-3 py-2 print:hidden">{banner}</div>}

      <Card className={step === STEP_REVIEW ? "print:shadow-none print:border-0" : ""}>
        {step === 0 && (
          <div className="space-y-5">
            <SectionDivider>Basic Details</SectionDivider>
            <div className="flex items-center gap-4">
              <div className="w-24 h-28 rounded-md border border-ink/15 bg-ink/5 overflow-hidden flex items-center justify-center shrink-0">
                {photoUrl ? (
                  <img src={photoUrl} alt="Employee photo" className="w-full h-full object-cover" />
                ) : (
                  <span className="text-[10px] text-ink/30 text-center px-1">No Photo</span>
                )}
              </div>
              <label>
                <span className={`inline-block px-3 py-1.5 rounded-md border border-ink/15 text-sm cursor-pointer hover:bg-ink/5 ${photoUploading ? "opacity-50 pointer-events-none" : ""}`}>
                  {photoUploading ? "Uploading…" : photoUrl ? "Replace Photo" : "Upload Photo"}
                </span>
                <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadPhoto(e.target.files[0])} />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="First Name" value={personal.first_name || ""} onChange={(e) => setPersonal({ ...personal, first_name: e.target.value })} />
              <Input label="Middle Name" value={personal.middle_name || ""} onChange={(e) => setPersonal({ ...personal, middle_name: e.target.value })} />
              <Input label="Last Name" value={personal.last_name || ""} onChange={(e) => setPersonal({ ...personal, last_name: e.target.value })} />
              <Input label="Father's/Husband's Name" value={personal.father_husband_name || ""} onChange={(e) => setPersonal({ ...personal, father_husband_name: e.target.value })} />
              <Select label="Gender" value={personal.gender || ""} onChange={(e) => setPersonal({ ...personal, gender: e.target.value })}>
                <option value="">Select...</option>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="OTHER">Other</option>
              </Select>
              <Input label="Date of Birth" type="date" value={personal.date_of_birth || ""} onChange={(e) => setPersonal({ ...personal, date_of_birth: e.target.value })} />
              <Select label="Marital Status" value={personal.marital_status || ""} onChange={(e) => setPersonal({ ...personal, marital_status: e.target.value })}>
                <option value="">Select...</option>
                <option value="SINGLE">Single</option>
                <option value="MARRIED">Married</option>
                <option value="OTHER">Other</option>
              </Select>
            </div>

            <SectionDivider>Education</SectionDivider>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Educational Qualification" value={personal.educational_qualification || ""} onChange={(e) => setPersonal({ ...personal, educational_qualification: e.target.value })} />
            </div>

            <SectionDivider>Contact Details</SectionDivider>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Mobile Number" value={personal.mobile_number || ""} maxLength={10}
                onChange={(e) => setPersonal({ ...personal, mobile_number: e.target.value.replace(/\D/g, "") })}
                error={formatError(personal.mobile_number, MOBILE_REGEX, "Must be 10 digits starting with 6-9")}
              />
              <Input
                label="Alternate Mobile" value={personal.alternate_mobile_number || ""} maxLength={10}
                onChange={(e) => setPersonal({ ...personal, alternate_mobile_number: e.target.value.replace(/\D/g, "") })}
                error={formatError(personal.alternate_mobile_number, MOBILE_REGEX, "Must be 10 digits starting with 6-9")}
              />
              <Input
                label="Personal Email" value={personal.personal_email || ""}
                onChange={(e) => setPersonal({ ...personal, personal_email: e.target.value })}
                error={formatError(personal.personal_email, EMAIL_REGEX, "Invalid email address")}
              />
              <Input
                label="Official Email" value={personal.official_email || ""}
                onChange={(e) => setPersonal({ ...personal, official_email: e.target.value })}
                error={formatError(personal.official_email, EMAIL_REGEX, "Invalid email address")}
              />
            </div>

            <SectionDivider>Identity Documents</SectionDivider>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Aadhaar"
                value={personal.aadhaar || ""}
                maxLength={12}
                onChange={(e) => setPersonal({ ...personal, aadhaar: e.target.value.replace(/\D/g, "") })}
                error={formatError(personal.aadhaar, AADHAAR_REGEX, "Must be 12 digits, not starting with 0 or 1")}
              />
              <Input
                label="PAN"
                value={personal.pan || ""}
                maxLength={10}
                onChange={(e) => setPersonal({ ...personal, pan: e.target.value.toUpperCase() })}
                error={formatError(personal.pan, PAN_REGEX, "Must be 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)")}
              />
            </div>

            <SectionDivider>Previous Experience</SectionDivider>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Previous Designation" value={personal.previous_designation || ""} onChange={(e) => setPersonal({ ...personal, previous_designation: e.target.value })} />
              <Input label="Previous Company Name" value={personal.previous_company_name || ""} onChange={(e) => setPersonal({ ...personal, previous_company_name: e.target.value })} />
              <Input label="Date of Joining (Previous Company)" type="date" value={personal.previous_date_of_joining || ""} onChange={(e) => setPersonal({ ...personal, previous_date_of_joining: e.target.value })} />
              <Input label="Total Experience (years)" type="number" step="0.1" value={personal.total_experience_years ?? ""} onChange={(e) => setPersonal({ ...personal, total_experience_years: e.target.value })} />
              <Input label="Previous Company Details" value={personal.previous_company_details || ""} onChange={(e) => setPersonal({ ...personal, previous_company_details: e.target.value })} className="col-span-2" />
            </div>

            <SectionDivider>Emergency Contact</SectionDivider>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Emergency Contact Name" value={personal.emergency_contact_name || ""} onChange={(e) => setPersonal({ ...personal, emergency_contact_name: e.target.value })} />
              <Input label="Emergency Contact Relationship" value={personal.emergency_contact_relationship || ""} onChange={(e) => setPersonal({ ...personal, emergency_contact_relationship: e.target.value })} />
              <Input
                label="Emergency Contact Mobile" value={personal.emergency_contact_mobile || ""} maxLength={10}
                onChange={(e) => setPersonal({ ...personal, emergency_contact_mobile: e.target.value.replace(/\D/g, "") })}
                error={formatError(personal.emergency_contact_mobile, MOBILE_REGEX, "Must be 10 digits starting with 6-9")}
              />
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <SectionDivider>Present Address</SectionDivider>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Address Line 1" value={address.present_line1 || ""} onChange={(e) => setAddress({ ...address, present_line1: e.target.value })} />
              <Input label="Address Line 2" value={address.present_line2 || ""} onChange={(e) => setAddress({ ...address, present_line2: e.target.value })} />
              <Input label="City" value={address.present_city || ""} onChange={(e) => setAddress({ ...address, present_city: e.target.value })} />
              <Input label="State" value={address.present_state || ""} onChange={(e) => setAddress({ ...address, present_state: e.target.value })} />
              <Input
                label="Pincode" value={address.present_pincode || ""} maxLength={6}
                onChange={(e) => setAddress({ ...address, present_pincode: e.target.value.replace(/\D/g, "") })}
                error={formatError(address.present_pincode, PINCODE_REGEX, "Must be 6 digits")}
              />
              <Input label="Country" value={address.present_country || ""} onChange={(e) => setAddress({ ...address, present_country: e.target.value })} />
            </div>

            <SectionDivider>Permanent Address</SectionDivider>
            <Checkbox
              label="Same as Present Address"
              checked={!!address.same_as_present}
              onChange={(e) => setAddress({ ...address, same_as_present: e.target.checked })}
            />
            {!address.same_as_present && (
              <div className="grid grid-cols-2 gap-4">
                <Input label="Address Line 1" value={address.permanent_line1 || ""} onChange={(e) => setAddress({ ...address, permanent_line1: e.target.value })} />
                <Input label="Address Line 2" value={address.permanent_line2 || ""} onChange={(e) => setAddress({ ...address, permanent_line2: e.target.value })} />
                <Input label="City" value={address.permanent_city || ""} onChange={(e) => setAddress({ ...address, permanent_city: e.target.value })} />
                <Input label="State" value={address.permanent_state || ""} onChange={(e) => setAddress({ ...address, permanent_state: e.target.value })} />
                <Input
                  label="Pincode" value={address.permanent_pincode || ""} maxLength={6}
                  onChange={(e) => setAddress({ ...address, permanent_pincode: e.target.value.replace(/\D/g, "") })}
                  error={formatError(address.permanent_pincode, PINCODE_REGEX, "Must be 6 digits")}
                />
                <Input label="Country" value={address.permanent_country || ""} onChange={(e) => setAddress({ ...address, permanent_country: e.target.value })} />
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="grid grid-cols-2 gap-4">
            <Input label="Employee Number" value={employment.employee_number?.startsWith("DRAFT-") ? "" : employment.employee_number || ""} onChange={(e) => setEmployment({ ...employment, employee_number: e.target.value })} />
            <Select label="Employment Type" value={employment.employment_type_id || ""} onChange={(e) => setEmployment({ ...employment, employment_type_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Select...</option>
              {masters.employeeTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
            <Select label="Employee Category" value={employment.employee_category_id || ""} onChange={(e) => setEmployment({ ...employment, employee_category_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Select...</option>
              {masters.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Designation" value={employment.designation_id || ""} onChange={(e) => setEmployment({ ...employment, designation_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Select...</option>
              {masters.designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
            <Select label="Work Location" value={employment.work_location_id || ""} onChange={(e) => setEmployment({ ...employment, work_location_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Select...</option>
              {masters.workLocations.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </Select>
            <Input label="Shift Group" value={employment.shift_group || ""} onChange={(e) => setEmployment({ ...employment, shift_group: e.target.value })} />
            <Input label="Date of Joining" type="date" value={employment.date_of_joining || ""} onChange={(e) => setEmployment({ ...employment, date_of_joining: e.target.value })} />
            <Input label="Confirmation Date" type="date" value={employment.confirmation_date || ""} onChange={(e) => setEmployment({ ...employment, confirmation_date: e.target.value })} />
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-ink mb-3">Organizational Assignment</h3>
              <div className="grid grid-cols-2 gap-4">
                <Select label="Cost Center" value={assignment.cost_center_id || ""} onChange={(e) => setAssignment({ ...assignment, cost_center_id: e.target.value })}>
                  <option value="">Select...</option>
                  {masters.costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
                <Select label="Project (optional)" value={assignment.project_id || ""} onChange={(e) => setAssignment({ ...assignment, project_id: e.target.value })}>
                  <option value="">None</option>
                  {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <Select label="Department" value={assignment.department_id || ""} onChange={(e) => setAssignment({ ...assignment, department_id: e.target.value })}>
                  <option value="">Select...</option>
                  {masters.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Select>
                <Input label="Effective From" type="date" value={assignment.effective_from} onChange={(e) => setAssignment({ ...assignment, effective_from: e.target.value })} />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-ink">Cost Allocation (blueprint §6)</h3>
                <AllocationTotalBadge total={allocationTotal} />
              </div>
              <p className="text-xs text-ink/40 mb-3">
                Independent from the Organizational Assignment above — split this employee's cost across multiple Cost Centers (and optionally Projects). Active allocations should total 100%.
              </p>

              {detail.allocations.filter((a) => !a.effective_to).length > 0 && (
                <table className="w-full text-sm mb-3">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-ink/40 border-b border-ink/10">
                      <th className="py-1.5 pr-3">Cost Center</th>
                      <th className="py-1.5 pr-3">Project</th>
                      <th className="py-1.5 pr-3">Percentage</th>
                      <th className="py-1.5 pr-3">Effective From</th>
                      <th className="py-1.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.allocations.filter((a) => !a.effective_to).map((a) => (
                      <tr key={a.id} className="border-b border-ink/5 last:border-0">
                        <td className="py-1.5 pr-3">{a.cost_center_name || "—"}</td>
                        <td className="py-1.5 pr-3">{a.project_name || "—"}</td>
                        <td className="py-1.5 pr-3">{a.percentage}%</td>
                        <td className="py-1.5 pr-3">{a.effective_from}</td>
                        <td className="py-1.5">
                          <Button variant="danger" size="sm" onClick={() => removeAllocation(a.id)} disabled={allocationBusy}>Remove</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {allocationError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{allocationError}</div>}

              <div className="grid grid-cols-4 gap-4 items-end">
                <Select label="Cost Center" value={allocation.cost_center_id} onChange={(e) => setAllocation({ ...allocation, cost_center_id: e.target.value })}>
                  <option value="">Select...</option>
                  {masters.costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
                <Select label="Project (optional)" value={allocation.project_id} onChange={(e) => setAllocation({ ...allocation, project_id: e.target.value })}>
                  <option value="">None</option>
                  {masters.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <Input label="Percentage" type="number" min="0" max="100" value={allocation.percentage} onChange={(e) => setAllocation({ ...allocation, percentage: e.target.value })} />
                <Input label="Effective From" type="date" value={allocation.effective_from} onChange={(e) => setAllocation({ ...allocation, effective_from: e.target.value })} />
              </div>
              <Button
                variant="outline"
                className="mt-3"
                onClick={addAllocation}
                disabled={allocationBusy || !allocation.cost_center_id || !allocation.percentage || !allocation.effective_from}
              >
                {allocationBusy ? "Adding…" : "+ Add Allocation"}
              </Button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-6">
            <div>
              <div className="flex items-center justify-between mb-3">
                <SectionDivider className="flex-1">PF</SectionDivider>
              </div>
              <Checkbox
                label="PF Eligible"
                checked={!!statutory.pf_eligible}
                onChange={(e) => setStatutory({ ...statutory, pf_eligible: e.target.checked })}
                className="mb-3"
              />
              <div className="grid grid-cols-3 gap-4">
                <Input
                  label="Name on File"
                  value={statutory.pf_name_on_file || ""}
                  disabled={!statutory.pf_eligible}
                  onChange={(e) => setStatutory({ ...statutory, pf_name_on_file: e.target.value })}
                />
                <Input
                  label="UAN / Member ID"
                  value={statutory.uan || ""}
                  disabled={!statutory.pf_eligible}
                  onChange={(e) => setStatutory({ ...statutory, uan: e.target.value })}
                />
                <Input
                  label="Effective Date"
                  type="date"
                  value={statutory.pf_effective_date || ""}
                  disabled={!statutory.pf_eligible}
                  onChange={(e) => setStatutory({ ...statutory, pf_effective_date: e.target.value })}
                />
              </div>
            </div>

            <div>
              <SectionDivider className="mb-3">ESI</SectionDivider>
              <Checkbox
                label="ESI Eligible"
                checked={!!statutory.esi_eligible}
                onChange={(e) => setStatutory({ ...statutory, esi_eligible: e.target.checked })}
                className="mb-3"
              />
              <div className="grid grid-cols-2 gap-4 mb-4">
                <Input
                  label="Mediclaim Number"
                  value={statutory.esi_mediclaim_number || ""}
                  disabled={!statutory.esi_eligible}
                  onChange={(e) => setStatutory({ ...statutory, esi_mediclaim_number: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <Input
                  label="Name on File"
                  value={statutory.esi_name_on_file || ""}
                  disabled={!statutory.esi_eligible}
                  onChange={(e) => setStatutory({ ...statutory, esi_name_on_file: e.target.value })}
                />
                <Input
                  label="ESI Number / Member ID"
                  value={statutory.esi_number || ""}
                  disabled={!statutory.esi_eligible}
                  onChange={(e) => setStatutory({ ...statutory, esi_number: e.target.value })}
                />
                <Input
                  label="Effective Date"
                  type="date"
                  value={statutory.esi_effective_date || ""}
                  disabled={!statutory.esi_eligible}
                  onChange={(e) => setStatutory({ ...statutory, esi_effective_date: e.target.value })}
                />
              </div>
            </div>

            <div>
              <SectionDivider className="mb-3">Other Eligibility</SectionDivider>
              <div className="flex gap-6 flex-wrap">
                <Checkbox label="Professional Tax Eligible" checked={!!statutory.pt_eligible} onChange={(e) => setStatutory({ ...statutory, pt_eligible: e.target.checked })} />
                <Checkbox label="Gratuity Eligible" checked={!!statutory.gratuity_eligible} onChange={(e) => setStatutory({ ...statutory, gratuity_eligible: e.target.checked })} />
              </div>
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="grid grid-cols-2 gap-4">
            <Input label="Bank Name" value={bank.bank_name || ""} onChange={(e) => setBank({ ...bank, bank_name: e.target.value })} />
            <Input label="Branch" value={bank.branch || ""} onChange={(e) => setBank({ ...bank, branch: e.target.value })} />
            <Input label="Account Number" value={bank.account_number || ""} onChange={(e) => setBank({ ...bank, account_number: e.target.value })} />
            <Input
              label="IFSC"
              value={bank.ifsc || ""}
              maxLength={11}
              onChange={(e) => setBank({ ...bank, ifsc: e.target.value.toUpperCase() })}
              error={formatError(bank.ifsc, IFSC_REGEX, "Must be 4 letters + 0 + 6 alphanumeric (e.g. SBIN0001234)")}
            />
            <Input label="Account Holder Name" value={bank.account_holder_name || ""} onChange={(e) => setBank({ ...bank, account_holder_name: e.target.value })} />
            <Select label="Account Type" value={bank.account_type || ""} onChange={(e) => setBank({ ...bank, account_type: e.target.value })}>
              <option value="">Select...</option>
              <option value="SAVINGS">Savings</option>
              <option value="CURRENT">Current</option>
            </Select>
            <Input label="Payment Mode" value={bank.payment_mode || ""} onChange={(e) => setBank({ ...bank, payment_mode: e.target.value })} />
            <Input label="Effective From" type="date" value={bank.effective_from} onChange={(e) => setBank({ ...bank, effective_from: e.target.value })} />
          </div>
        )}

        {step === 6 && (
          <div className="space-y-4">
            <p className="text-xs text-ink/40">
              Documents requested here are resolved from Employee Type / Category / Designation via Document Configuration (blueprint §14).
              Set Employment Information (step 3) first so the correct list shows.
            </p>
            {docError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{docError}</div>}
            {requiredDocs.length === 0 && (
              <p className="text-sm text-ink/40 py-6 text-center">No document requirements configured for this employee's Type/Category/Designation.</p>
            )}
            <div className="space-y-2">
              {requiredDocs.map((d) => (
                <div key={d.document_type_id} className="border border-ink/10 rounded-md p-3 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-ink flex items-center gap-2">
                      {d.document_type_name}
                      {d.is_mandatory ? (
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-danger/10 text-danger">Mandatory</span>
                      ) : (
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-ink/5 text-ink/50">Optional</span>
                      )}
                    </div>
                    {d.uploaded ? (
                      <div className="text-xs text-ink/50 mt-0.5">{d.file_name} · {d.verification_status}</div>
                    ) : (
                      <div className="text-xs text-ink/40 mt-0.5">Not uploaded</div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {d.uploaded && (
                      <>
                        <Button variant="outline" size="sm" onClick={() => downloadDocument(d.document_meta_id, d.file_name)}>Download</Button>
                        <Button variant="danger" size="sm" onClick={() => removeDocument(d.document_meta_id)}>Remove</Button>
                      </>
                    )}
                    <label className="text-xs">
                      <span className={`inline-block px-3 py-1.5 rounded-md border border-ink/15 cursor-pointer hover:bg-ink/5 ${docUploadingId === d.document_type_id ? "opacity-50 pointer-events-none" : ""}`}>
                        {docUploadingId === d.document_type_id ? "Uploading…" : d.uploaded ? "Replace" : "Upload"}
                      </span>
                      <input
                        type="file"
                        className="hidden"
                        onChange={(e) => uploadDocument(d.document_type_id, e.target.files[0])}
                      />
                    </label>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {step === 7 && (
          <div className="space-y-8">
            <div>
              <h3 className="text-sm font-semibold text-ink mb-3">Dependents</h3>

              {detail.dependents.length > 0 && (
                <table className="w-full text-sm mb-3">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-ink/40 border-b border-ink/10">
                      <th className="py-1.5 pr-3">Name</th>
                      <th className="py-1.5 pr-3">Relationship</th>
                      <th className="py-1.5 pr-3">Date of Birth</th>
                      <th className="py-1.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.dependents.map((d) => (
                      <tr key={d.id} className="border-b border-ink/5 last:border-0">
                        <td className="py-1.5 pr-3">{d.name}</td>
                        <td className="py-1.5 pr-3">{d.relationship_type || "—"}</td>
                        <td className="py-1.5 pr-3">{formatDate(d.date_of_birth)}</td>
                        <td className="py-1.5">
                          <Button variant="danger" size="sm" onClick={() => removeDependent(d.id)} disabled={dependentBusy}>Remove</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {dependentError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{dependentError}</div>}

              <div className="grid grid-cols-4 gap-4 items-end">
                <Input label="Name" value={dependent.name} onChange={(e) => setDependent({ ...dependent, name: e.target.value })} />
                <Input label="Relationship" value={dependent.relationship_type || ""} onChange={(e) => setDependent({ ...dependent, relationship_type: e.target.value })} />
                <Input label="Date of Birth" type="date" value={dependent.date_of_birth || ""} onChange={(e) => setDependent({ ...dependent, date_of_birth: e.target.value })} />
              </div>
              <Button
                variant="outline"
                className="mt-3"
                onClick={addDependent}
                disabled={dependentBusy || !dependent.name}
              >
                {dependentBusy ? "Adding…" : "+ Add Dependent"}
              </Button>
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-ink">Nominees</h3>
                {nominee.nomination_type && (
                  <AllocationTotalBadge total={nomineeTotalForType} />
                )}
              </div>
              <p className="text-xs text-ink/40 mb-3">
                Nomination percentage pools are independent per type — PF, Gratuity, Insurance, and Other each total their own 100%.
              </p>

              {detail.nominees.length > 0 && (
                <table className="w-full text-sm mb-3">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-ink/40 border-b border-ink/10">
                      <th className="py-1.5 pr-3">Name</th>
                      <th className="py-1.5 pr-3">Type</th>
                      <th className="py-1.5 pr-3">Percentage</th>
                      <th className="py-1.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.nominees.map((n) => (
                      <tr key={n.id} className="border-b border-ink/5 last:border-0">
                        <td className="py-1.5 pr-3">{n.name}</td>
                        <td className="py-1.5 pr-3">{n.nomination_type || "—"}</td>
                        <td className="py-1.5 pr-3">{n.percentage ?? "—"}%</td>
                        <td className="py-1.5">
                          <Button variant="danger" size="sm" onClick={() => removeNominee(n.id)} disabled={nomineeBusy}>Remove</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {nomineeError && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{nomineeError}</div>}

              <div className="grid grid-cols-4 gap-4 items-end">
                <Input label="Name" value={nominee.name} onChange={(e) => setNominee({ ...nominee, name: e.target.value })} />
                <Select label="Nomination Type" value={nominee.nomination_type || ""} onChange={(e) => setNominee({ ...nominee, nomination_type: e.target.value })}>
                  <option value="">Select...</option>
                  <option value="PF">PF</option>
                  <option value="GRATUITY">Gratuity</option>
                  <option value="INSURANCE">Insurance</option>
                  <option value="OTHER">Other</option>
                </Select>
                <Input label="Percentage" type="number" min="0" max="100" value={nominee.percentage || ""} onChange={(e) => setNominee({ ...nominee, percentage: e.target.value })} />
              </div>
              <Button
                variant="outline"
                className="mt-3"
                onClick={addNominee}
                disabled={nomineeBusy || !nominee.name}
              >
                {nomineeBusy ? "Adding…" : "+ Add Nominee"}
              </Button>
            </div>
          </div>
        )}

        {STEP_DRIVING_LICENCE >= 0 && step === STEP_DRIVING_LICENCE && (
          <div className="space-y-4">
            <p className="text-xs text-ink/40">
              Shown because a Document Configuration rule matches this employee's Employee Type/Category/Designation
              {dlRequirement.is_required ? " — treated as required for this employee." : " (optional for this employee)."}
            </p>
            <div className="grid grid-cols-2 gap-4">
              <Input label="Licence Number" value={drivingLicence.licence_number || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, licence_number: e.target.value })} />
              <Input label="Badge Number" value={drivingLicence.badge_number || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, badge_number: e.target.value })} />
              <Input label="Vehicle Class" value={drivingLicence.vehicle_class || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, vehicle_class: e.target.value })} placeholder="e.g. LMV, HMV" />
              <Input label="Issuing Authority" value={drivingLicence.issuing_authority || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, issuing_authority: e.target.value })} />
              <Input label="Issue Date" type="date" value={drivingLicence.issue_date || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, issue_date: e.target.value })} />
              <Input label="Expiry Date" type="date" value={drivingLicence.expiry_date || ""} onChange={(e) => setDrivingLicence({ ...drivingLicence, expiry_date: e.target.value })} />
            </div>
          </div>
        )}

        {step === STEP_REVIEW && (
          <div className="space-y-6 text-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between print:hidden">
                  <h3 className="text-sm font-semibold text-ink">Review Application</h3>
                  <Button variant="outline" size="sm" onClick={() => window.print()}>Print / Save as PDF</Button>
                </div>

                <div className="hidden print:block text-center">
                  <div className="text-lg font-display font-semibold text-ink">Employee Registration Application</div>
                  <div className="text-xs text-ink/50 mt-0.5">
                    {personal.first_name} {personal.last_name} · {employment.employee_number} · Printed {formatDate(new Date().toISOString().slice(0, 10))}
                  </div>
                </div>
              </div>

              {photoUrl && (
                <img
                  src={photoUrl}
                  alt="Employee photo"
                  className="w-20 h-24 object-cover rounded-md border border-ink/15 shrink-0"
                />
              )}
            </div>

            <SectionDivider>Personal Information</SectionDivider>
            <div className="grid grid-cols-3 gap-3">
              <Field label="First Name" value={personal.first_name} />
              <Field label="Middle Name" value={personal.middle_name} />
              <Field label="Last Name" value={personal.last_name} />
              <Field label="Father's/Husband's Name" value={personal.father_husband_name} />
              <Field label="Gender" value={personal.gender} />
              <Field label="Date of Birth" value={formatDate(personal.date_of_birth)} />
              <Field label="Marital Status" value={personal.marital_status} />
              <Field label="Educational Qualification" value={personal.educational_qualification} />
            </div>

            <SectionDivider>Previous Experience</SectionDivider>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Previous Designation" value={personal.previous_designation} />
              <Field label="Previous Company Name" value={personal.previous_company_name} />
              <Field label="Date of Joining (Previous Company)" value={formatDate(personal.previous_date_of_joining)} />
              <Field label="Total Experience" value={personal.total_experience_years != null && personal.total_experience_years !== "" ? `${personal.total_experience_years} years` : null} />
              <Field label="Previous Company Details" value={personal.previous_company_details} />
            </div>

            <SectionDivider>Contact Details</SectionDivider>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Mobile Number" value={personal.mobile_number} />
              <Field label="Alternate Mobile" value={personal.alternate_mobile_number} />
              <Field label="Personal Email" value={personal.personal_email} />
              <Field label="Official Email" value={personal.official_email} />
            </div>

            <SectionDivider>Identity Documents</SectionDivider>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Aadhaar" value={personal.aadhaar} />
              <Field label="PAN" value={personal.pan} />
            </div>

            <SectionDivider>Emergency Contact</SectionDivider>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Name" value={personal.emergency_contact_name} />
              <Field label="Relationship" value={personal.emergency_contact_relationship} />
              <Field label="Mobile" value={personal.emergency_contact_mobile} />
            </div>

            <SectionDivider>Address</SectionDivider>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Present Address" value={[address.present_line1, address.present_line2, address.present_city, address.present_state, address.present_pincode, address.present_country].filter(Boolean).join(", ")} />
              <Field
                label="Permanent Address"
                value={address.same_as_present ? "Same as Present Address" : [address.permanent_line1, address.permanent_line2, address.permanent_city, address.permanent_state, address.permanent_pincode, address.permanent_country].filter(Boolean).join(", ")}
              />
            </div>

            <SectionDivider>Employment Information</SectionDivider>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Employee Number" value={employment.employee_number?.startsWith("DRAFT-") ? null : employment.employee_number} />
              <Field label="Employment Type" value={employment.employment_type} />
              <Field label="Employee Category" value={employment.employee_category} />
              <Field label="Designation" value={employment.designation} />
              <Field label="Work Location" value={employment.work_location} />
              <Field label="Shift Group" value={employment.shift_group} />
              <Field label="Date of Joining" value={formatDate(employment.date_of_joining)} />
              <Field label="Confirmation Date" value={formatDate(employment.confirmation_date)} />
            </div>

            <SectionDivider>Organizational Assignment</SectionDivider>
            <div className="space-y-2">
              {detail.assignments.length === 0 && <p className="text-ink/40 text-xs">No organizational assignment recorded.</p>}
              {detail.assignments.map((a) => (
                <div key={a.id} className="text-xs text-ink/70">
                  {masters.costCenters.find((c) => c.id === a.cost_center_id)?.name || `Cost Center #${a.cost_center_id}`}
                  {" · "}{masters.departments.find((d) => d.id === a.department_id)?.name || `Department #${a.department_id}`}
                  {a.project_id ? ` · ${masters.projects.find((p) => p.id === a.project_id)?.name || `Project #${a.project_id}`}` : ""}
                  {" — "}{formatDate(a.effective_from)} to {a.effective_to ? formatDate(a.effective_to) : "present"}
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink/40">Cost Allocation</span>
              <AllocationTotalBadge total={allocationTotal} />
            </div>
            <div className="space-y-1">
              {detail.allocations.filter((a) => !a.effective_to).length === 0 && <p className="text-ink/40 text-xs">No cost allocation recorded.</p>}
              {detail.allocations.filter((a) => !a.effective_to).map((a) => (
                <div key={a.id} className="text-xs text-ink/70">{a.percentage}% — {a.cost_center_name}{a.project_name ? ` · ${a.project_name}` : ""}</div>
              ))}
            </div>

            <SectionDivider>Statutory Information</SectionDivider>
            {detail.statutory.length === 0 && <p className="text-ink/40 text-xs">No statutory information recorded.</p>}
            {detail.statutory.map((s) => (
              <div key={s.id} className="space-y-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold uppercase tracking-wide text-ink/40">PF</span>
                    <StatusBadge status={s.pf_eligible ? "ACTIVE" : "INACTIVE"} />
                  </div>
                  {s.pf_eligible ? (
                    <div className="grid grid-cols-3 gap-3">
                      <Field label="Name on File" value={s.pf_name_on_file} />
                      <Field label="UAN / Member ID" value={s.uan} />
                      <Field label="Effective Date" value={formatDate(s.pf_effective_date)} />
                    </div>
                  ) : <p className="text-ink/40 text-xs">Not eligible.</p>}
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold uppercase tracking-wide text-ink/40">ESI</span>
                    <StatusBadge status={s.esi_eligible ? "ACTIVE" : "INACTIVE"} />
                  </div>
                  {s.esi_eligible ? (
                    <div className="grid grid-cols-3 gap-3">
                      <Field label="Name on File" value={s.esi_name_on_file} />
                      <Field label="ESI Number / Member ID" value={s.esi_number} />
                      <Field label="Mediclaim Number" value={s.esi_mediclaim_number} />
                      <Field label="Effective Date" value={formatDate(s.esi_effective_date)} />
                    </div>
                  ) : <p className="text-ink/40 text-xs">Not eligible.</p>}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Professional Tax Eligible" value={s.pt_eligible ? "Yes" : "No"} />
                  <Field label="Gratuity Eligible" value={s.gratuity_eligible ? "Yes" : "No"} />
                </div>
              </div>
            ))}

            <SectionDivider>Bank Information</SectionDivider>
            <div className="space-y-1">
              {detail.bank_accounts.length === 0 && <p className="text-ink/40 text-xs">No bank account recorded.</p>}
              {detail.bank_accounts.map((b) => (
                <div key={b.id} className="text-xs text-ink/70">
                  {b.bank_name} — {b.account_number} ({b.ifsc}) {b.is_primary ? "· Primary" : ""} · Verification: {b.verification_status}
                </div>
              ))}
            </div>

            {STEP_DRIVING_LICENCE >= 0 && (
              <>
                <SectionDivider>Driving Licence</SectionDivider>
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Licence Number" value={drivingLicence.licence_number} />
                  <Field label="Badge Number" value={drivingLicence.badge_number} />
                  <Field label="Vehicle Class" value={drivingLicence.vehicle_class} />
                  <Field label="Issuing Authority" value={drivingLicence.issuing_authority} />
                  <Field label="Issue Date" value={formatDate(drivingLicence.issue_date)} />
                  <Field label="Expiry Date" value={formatDate(drivingLicence.expiry_date)} />
                </div>
              </>
            )}

            <SectionDivider>Documents / Attachments</SectionDivider>
            <div className="space-y-1">
              {requiredDocs.length === 0 && <p className="text-ink/40 text-xs">No document requirements configured for this employee.</p>}
              {requiredDocs.map((d) => (
                <div key={d.document_type_id} className="text-xs text-ink/70 flex items-center gap-2">
                  <span className="font-medium text-ink">{d.document_type_name}</span>
                  <span className="text-ink/40">({d.is_mandatory ? "Mandatory" : "Optional"})</span>
                  {d.uploaded ? <span>— {d.file_name}</span> : <span className="text-warn">— Not uploaded</span>}
                </div>
              ))}
            </div>

            <SectionDivider>Dependents</SectionDivider>
            <div className="space-y-1">
              {detail.dependents.length === 0 && <p className="text-ink/40 text-xs">No dependents recorded.</p>}
              {detail.dependents.map((d) => <div key={d.id} className="text-xs text-ink/70">{d.name} — {d.relationship_type || "—"}</div>)}
            </div>

            <SectionDivider>Nominees</SectionDivider>
            <div className="space-y-1">
              {detail.nominees.length === 0 && <p className="text-ink/40 text-xs">No nominees recorded.</p>}
              {detail.nominees.map((n) => <div key={n.id} className="text-xs text-ink/70">{n.name} — {n.nomination_type || "—"} ({n.percentage ?? "—"}%)</div>)}
            </div>

            <SectionDivider>Status</SectionDivider>
            {detail.episode.status === "DRAFT" ? (
              <p className="text-ink/40 text-xs">Submitting moves this record from Draft to Pending Approval (blueprint §8). Completion of the wizard does not make the employee active — approval is required.</p>
            ) : (
              <p className="text-ink/40 text-xs">This employee is already {detail.episode.status.replace(/_/g, " ").toLowerCase()}. Edits to Personal/Employment Information above may require Approver review (blueprint §15) — see Change Requests.</p>
            )}
          </div>
        )}
      </Card>

      <div className="flex justify-between print:hidden">
        <Button variant="outline" onClick={() => goToStep(Math.max(0, step - 1))} disabled={step === 0}>
          Back
        </Button>
        {step < steps.length - 1 ? (
          <Button onClick={next} disabled={saving || currentStepHasError}>{saving ? "Saving…" : "Save & Continue"}</Button>
        ) : detail.episode.status === "DRAFT" ? (
          <Button variant="accent" onClick={submit} disabled={saving}>{saving ? "Submitting…" : "Submit for Approval"}</Button>
        ) : (
          <Button variant="accent" onClick={() => navigate(`/employees/${episodeId}`)}>Done</Button>
        )}
      </div>
    </div>
  );
}

function AllocationTotalBadge({ total }) {
  const cls = total === 100 ? "bg-ok/10 text-ok" : total > 100 ? "bg-danger/10 text-danger" : "bg-warn/10 text-warn";
  return <span className={`text-xs font-medium px-2 py-1 rounded-full ${cls}`}>{total}% allocated</span>;
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-ink/40">{label}</div>
      <div className="text-ink text-sm">{value || value === 0 ? value : "—"}</div>
    </div>
  );
}
