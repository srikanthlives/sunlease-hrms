import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client, { apiErrorMessage } from "../api/client";
import { Card, Button, Input, Select, Table, StatusBadge, SectionDivider, formatDate } from "../components/ui";

const STATUS_OPTIONS = ["APPLIED", "IN_PROGRESS", "APPROVED", "REJECTED", "CONVERTED", "WITHDRAWN"];

const EMPTY_FORM = {
  first_name: "", middle_name: "", last_name: "", father_husband_name: "", gender: "", date_of_birth: "",
  mobile_number: "", alternate_mobile_number: "", personal_email: "", educational_qualification: "", aadhaar: "",
  current_designation: "", current_company_name: "", current_company_details: "", current_date_of_joining: "", total_experience_years: "",
  applied_designation_id: "", applied_employee_category_id: "",
  applied_cost_center_id: "", applied_project_id: "",
  applied_date: new Date().toISOString().slice(0, 10),
};

export default function Candidates() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState([]);
  const [designations, setDesignations] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [categories, setCategories] = useState([]);
  const [projects, setProjects] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  function reload() {
    const params = {};
    if (statusFilter) params.status_ = statusFilter;
    client.get("/recruitment/candidates", { params }).then((res) => setCandidates(res.data)).catch((err) => setError(apiErrorMessage(err)));
  }
  useEffect(reload, [statusFilter]);

  useEffect(() => {
    client.get("/designations").then((res) => setDesignations(res.data));
    client.get("/cost-centers").then((res) => setCostCenters(res.data));
    client.get("/employee-categories").then((res) => setCategories(res.data));
    client.get("/projects").then((res) => setProjects(res.data));
  }, []);

  async function createCandidate() {
    setError("");
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        date_of_birth: form.date_of_birth || null,
        current_date_of_joining: form.current_date_of_joining || null,
        total_experience_years: form.total_experience_years === "" ? null : Number(form.total_experience_years),
        applied_designation_id: Number(form.applied_designation_id),
        applied_employee_category_id: form.applied_employee_category_id ? Number(form.applied_employee_category_id) : null,
        applied_cost_center_id: Number(form.applied_cost_center_id),
        applied_project_id: form.applied_project_id ? Number(form.applied_project_id) : null,
      };
      const res = await client.post("/recruitment/candidates", payload);
      if (res.data.aadhaar_duplicate_warning?.length > 0) {
        window.alert(`Aadhaar number warning — this Aadhaar also matches:\n\n${res.data.aadhaar_duplicate_warning.join("\n")}`);
      }
      setShowNew(false);
      setForm(EMPTY_FORM);
      navigate(`/recruitment/candidates/${res.data.id}`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const columns = [
    { key: "reference_number", header: "Reference #" },
    { key: "name", header: "Name", render: (r) => `${r.first_name} ${r.last_name}` },
    { key: "designation_name", header: "Applied For", render: (r) => r.designation_name || "—" },
    { key: "cost_center_name", header: "Cost Center", render: (r) => r.cost_center_name || "—" },
    { key: "applied_date", header: "Applied On", render: (r) => formatDate(r.applied_date) },
    { key: "mobile_number", header: "Mobile", render: (r) => r.mobile_number || "—" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
  ];

  const canCreate = form.first_name && form.last_name && form.applied_designation_id && form.applied_cost_center_id;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-display font-semibold text-ink">Candidates</h1>
          <p className="text-sm text-ink/50 mt-1">Recruitment pipeline — tracked by reference number until converted to an employee.</p>
        </div>
        <Button onClick={() => setShowNew((s) => !s)}>{showNew ? "Cancel" : "New Candidate"}</Button>
      </div>
      {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2">{error}</div>}

      {showNew && (
        <Card>
          <h2 className="text-sm font-semibold text-ink mb-1">New Candidate</h2>
          <p className="text-xs text-ink/40 mb-3">A reference number is generated automatically once created — used as the temp application number until this candidate is converted to an employee.</p>

          <SectionDivider>Personal Information</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="First Name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            <Input label="Middle Name" value={form.middle_name} onChange={(e) => setForm({ ...form, middle_name: e.target.value })} />
            <Input label="Last Name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            <Input label="Father's/Husband's Name" value={form.father_husband_name} onChange={(e) => setForm({ ...form, father_husband_name: e.target.value })} />
            <Select label="Gender" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
              <option value="">Select...</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
              <option value="OTHER">Other</option>
            </Select>
            <Input type="date" label="Date of Birth" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} />
            <Input label="Mobile Number" value={form.mobile_number} onChange={(e) => setForm({ ...form, mobile_number: e.target.value })} />
            <Input label="Alternate Mobile Number" value={form.alternate_mobile_number} onChange={(e) => setForm({ ...form, alternate_mobile_number: e.target.value })} />
            <Input label="Email" value={form.personal_email} onChange={(e) => setForm({ ...form, personal_email: e.target.value })} />
            <Input label="Educational Qualification" value={form.educational_qualification} onChange={(e) => setForm({ ...form, educational_qualification: e.target.value })} />
            <Input label="Aadhaar Number" value={form.aadhaar} onChange={(e) => setForm({ ...form, aadhaar: e.target.value })} />
          </div>

          <SectionDivider>Current Experience</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="Current Designation" value={form.current_designation} onChange={(e) => setForm({ ...form, current_designation: e.target.value })} />
            <Input label="Current Company Name" value={form.current_company_name} onChange={(e) => setForm({ ...form, current_company_name: e.target.value })} />
            <Input type="date" label="Date of Joining (Current Company)" value={form.current_date_of_joining} onChange={(e) => setForm({ ...form, current_date_of_joining: e.target.value })} />
            <Input type="number" step="0.1" label="Total Experience (years)" value={form.total_experience_years} onChange={(e) => setForm({ ...form, total_experience_years: e.target.value })} />
            <Input label="Current Company Details" value={form.current_company_details} onChange={(e) => setForm({ ...form, current_company_details: e.target.value })} className="col-span-2" />
          </div>

          <SectionDivider>Employment Information</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Input label="Application Reference Number" value="Auto-generated on save" disabled />
            <Select label="Employee Category" value={form.applied_employee_category_id} onChange={(e) => setForm({ ...form, applied_employee_category_id: e.target.value })}>
              <option value="">Select...</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Designation" value={form.applied_designation_id} onChange={(e) => setForm({ ...form, applied_designation_id: e.target.value })}>
              <option value="">Select...</option>
              {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
            <Input type="date" label="Applied Date" value={form.applied_date} onChange={(e) => setForm({ ...form, applied_date: e.target.value })} />
          </div>

          <SectionDivider>Organizational Assignment</SectionDivider>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <Select label="Cost Center" value={form.applied_cost_center_id} onChange={(e) => setForm({ ...form, applied_cost_center_id: e.target.value })}>
              <option value="">Select...</option>
              {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select label="Project" value={form.applied_project_id} onChange={(e) => setForm({ ...form, applied_project_id: e.target.value })}>
              <option value="">None</option>
              {projects.filter((p) => !form.applied_cost_center_id || p.cost_center_id === Number(form.applied_cost_center_id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>

          <Button onClick={createCandidate} disabled={!canCreate || submitting}>{submitting ? "Creating…" : "Create Candidate"}</Button>
          <p className="text-xs text-ink/40 mt-2">Documents can be uploaded from the candidate's page after creation, based on what's configured for the selected Designation/Category.</p>
        </Card>
      )}

      <Card>
        <div className="w-56 mb-3">
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All Statuses</option>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
        </div>
        <Table columns={columns} rows={candidates} onRowClick={(r) => navigate(`/recruitment/candidates/${r.id}`)} empty="No candidates yet." />
      </Card>
    </div>
  );
}
