import { useEffect, useState } from 'react'
import api from '../api'
import { useAuth } from '../auth/AuthContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select } from '../components/ui/select'
import { Badge } from '../components/ui/badge'
import { Dialog } from '../components/ui/dialog'
import { Alert } from '../components/ui/alert'
import { Plus, Pencil, Trash2, UploadCloud, History } from 'lucide-react'
import { MONTH_NAMES } from '../lib/utils'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, applyEmployeeFilters } from '../period/EmployeeFilterContext'

const EMPTY = {
  employee_code: '', first_name: '', last_name: '', email: '', phone: '',
  department: '', designation: '', location: '', date_of_joining: '', status: 'active',
  template_id: '', bank_name: '', bank_account: '', ifsc: '', pan: '', uan: '',
  pf_eligible: true, eps_eligible: true, esi_number: '', esi_eligible: true,
  mediclaim_policy_no: '', mediclaim_eligible: true,
}

export default function Employees() {
  const { user } = useAuth()
  const { month, year } = usePeriod()
  const isAdmin = user?.role === 'admin'
  const filters = useEmployeeFilters()
  const [employees, setEmployees] = useState([])
  const [templates, setTemplates] = useState([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')

  const [uploadFile, setUploadFile] = useState(null)
  const [uploadResult, setUploadResult] = useState(null)
  const [uploadError, setUploadError] = useState('')

  const [assignEmployee, setAssignEmployee] = useState(null)
  const [assignments, setAssignments] = useState([])
  const [assignForm, setAssignForm] = useState({ template_id: '', effective_month: new Date().getMonth() + 1, effective_year: new Date().getFullYear() })
  const [assignError, setAssignError] = useState('')

  function load() {
    api.get('/employees/eligible', { params: { month, year } }).then((r) => setEmployees(r.data))
    api.get('/templates').then((r) => setTemplates(r.data))
  }
  useEffect(load, [month, year])

  function templatesForLocation(location) {
    const loc = (location || '').trim()
    return templates.filter((t) => (loc ? t.location === loc : !t.location))
  }

  function openCreate() {
    setEditing(null)
    setForm(EMPTY)
    setError('')
    setOpen(true)
  }
  function openEdit(emp) {
    setEditing(emp)
    setForm({ ...emp, template_id: emp.template_id || '' })
    setError('')
    setOpen(true)
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    try {
      const payload = {
        ...form,
        template_id: form.template_id ? Number(form.template_id) : null,
        email: form.email ? form.email.trim() : null,
        pf_eligible: form.pf_eligible === true || form.pf_eligible === 'true',
        eps_eligible: form.eps_eligible === true || form.eps_eligible === 'true',
        esi_eligible: form.esi_eligible === true || form.esi_eligible === 'true',
        mediclaim_eligible: form.mediclaim_eligible === true || form.mediclaim_eligible === 'true',
      }
      if (editing) {
        await api.put(`/employees/${editing.id}`, payload)
      } else {
        await api.post('/employees', payload)
      }
      setOpen(false)
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save employee')
    }
  }

  async function removeEmployee(emp) {
    if (!window.confirm(`Delete ${emp.employee_code} · ${emp.first_name} ${emp.last_name}? This also removes their attendance, payslips, overrides and login account. This cannot be undone.`)) return
    try {
      await api.delete(`/employees/${emp.id}`)
      load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete employee')
    }
  }

  async function doUpload() {
    setUploadError(''); setUploadResult(null)
    if (!uploadFile) return
    const formData = new FormData()
    formData.append('file', uploadFile)
    try {
      const { data } = await api.post('/employees/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadResult(data)
      load()
    } catch (err) {
      setUploadError(err.response?.data?.detail || 'Upload failed')
    }
  }

  function openAssignments(emp) {
    setAssignEmployee(emp)
    setAssignError('')
    setAssignForm({ template_id: '', effective_month: new Date().getMonth() + 1, effective_year: new Date().getFullYear() })
    api.get(`/employees/${emp.id}/template-assignments`).then((r) => setAssignments(r.data))
  }

  async function addAssignment(e) {
    e.preventDefault()
    setAssignError('')
    try {
      await api.post(`/employees/${assignEmployee.id}/template-assignments`, {
        template_id: Number(assignForm.template_id),
        effective_month: Number(assignForm.effective_month),
        effective_year: Number(assignForm.effective_year),
      })
      const r = await api.get(`/employees/${assignEmployee.id}/template-assignments`)
      setAssignments(r.data)
    } catch (err) {
      setAssignError(err.response?.data?.detail || 'Failed to add assignment')
    }
  }

  async function removeAssignment(assignmentId) {
    if (!window.confirm('Remove this template assignment?')) return
    await api.delete(`/employees/${assignEmployee.id}/template-assignments/${assignmentId}`)
    const r = await api.get(`/employees/${assignEmployee.id}/template-assignments`)
    setAssignments(r.data)
  }

  const displayedEmployees = applyEmployeeFilters(employees, filters, (e) => e)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold">Employees</h1>
          <p className="text-sm text-muted-foreground">Manage employee records and salary template assignment.</p>
        </div>
        {isAdmin && (
          <Button onClick={openCreate}><Plus className="h-4 w-4" /> Add employee</Button>
        )}
      </div>

      {isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Bulk upload employees (Excel)</CardTitle>
            <CardDescription>
              Required columns: employee_code, first_name. Optional: last_name, email, phone, department,
              designation, location, date_of_joining, template_no (assigns that template as their default), bank_name,
              bank_account, ifsc, pan, uan. Existing employees are matched and updated by employee_code.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-3">
            <input type="file" accept=".xlsx,.xls" onChange={(e) => setUploadFile(e.target.files[0])} className="text-sm" />
            <Button onClick={doUpload}><UploadCloud className="h-4 w-4" /> Upload</Button>
          </CardContent>
          {uploadError && <CardContent className="pt-0"><Alert variant="destructive">{uploadError}</Alert></CardContent>}
          {uploadResult && (
            <CardContent className="pt-0">
              <Alert variant="success">Inserted {uploadResult.inserted}, updated {uploadResult.updated}.</Alert>
              {uploadResult.errors.length > 0 && (
                <Alert variant="destructive" className="mt-2">
                  {uploadResult.errors.map((e, i) => <div key={i}>{e}</div>)}
                </Alert>
              )}
            </CardContent>
          )}
        </Card>
      )}

      <Card>
        <CardContent className="pt-5">
          {(filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter) && (
            <p className="mb-3 text-xs text-muted-foreground">
              Filtered/sorted via the "Employee filters" bar above — showing {displayedEmployees.length} of {employees.length}.
            </p>
          )}
          <Table>
            <THead>
              <TR>
                <TH>Code</TH><TH>Name</TH><TH>Department</TH><TH>Designation</TH><TH>Location</TH>
                <TH>Default Template</TH><TH>Joined</TH><TH>Last working day</TH><TH>Status</TH>{isAdmin && <TH></TH>}
              </TR>
            </THead>
            <TBody>
              {displayedEmployees.map((emp) => (
                <TR key={emp.id}>
                  <TD className="font-mono-num">{emp.employee_code}</TD>
                  <TD>{emp.first_name} {emp.last_name}</TD>
                  <TD>{emp.department || '—'}</TD>
                  <TD>{emp.designation || '—'}</TD>
                  <TD>{emp.location || '—'}</TD>
                  <TD>{emp.template ? `${emp.template.template_no} · ${emp.template.name}` : <span className="text-muted-foreground">Unassigned</span>}</TD>
                  <TD className="font-mono-num text-muted-foreground">{emp.date_of_joining || '—'}</TD>
                  <TD className="font-mono-num text-muted-foreground">{emp.date_of_leaving || '—'}</TD>
                  <TD>
                    <Badge variant={emp.status === 'active' ? 'success' : 'muted'}>{emp.status}</Badge>
                  </TD>
                  {isAdmin && (
                    <TD>
                      <div className="flex items-center gap-0.5">
                        <Button variant="ghost" size="icon" onClick={() => openAssignments(emp)} title="Template history / effective dates">
                          <History className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => openEdit(emp)} title="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => removeEmployee(emp)} title="Delete">
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TD>
                  )}
                </TR>
              ))}
              {employees.length === 0 && (
                <TR><TD colSpan={10} className="py-8 text-center text-muted-foreground">No employees yet.</TD></TR>
              )}
              {employees.length > 0 && displayedEmployees.length === 0 && (
                <TR><TD colSpan={10} className="py-8 text-center text-muted-foreground">No employees match the current filters.</TD></TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={open} onClose={() => setOpen(false)} title={editing ? 'Edit employee' : 'Add employee'}>
        <form onSubmit={submit} className="space-y-4">
          {error && <Alert variant="destructive">{error}</Alert>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Employee code">
              <Input required value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value })} />
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                <option value="active">Active</option>
                <option value="resigned">Resigned</option>
                <option value="terminated">Terminated</option>
              </Select>
            </Field>
            <Field label="First name">
              <Input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            </Field>
            <Field label="Last name">
              <Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            </Field>
            <Field label="Email (optional)">
              <Input type="email" value={form.email || ''} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Phone">
              <Input value={form.phone || ''} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <Field label="Department">
              <Input value={form.department || ''} onChange={(e) => setForm({ ...form, department: e.target.value })} />
            </Field>
            <Field label="Designation">
              <Input value={form.designation || ''} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
            </Field>
            <Field label="Location">
              <Input value={form.location || ''} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="e.g. Mumbai" />
            </Field>
            <Field label="Date of joining">
              <Input type="date" value={form.date_of_joining || ''} onChange={(e) => setForm({ ...form, date_of_joining: e.target.value })} />
            </Field>
            <Field label="Date of leaving">
              <Input type="date" value={form.date_of_leaving || ''} onChange={(e) => setForm({ ...form, date_of_leaving: e.target.value })} />
            </Field>
            <Field label="Default salary template">
              <Select value={form.template_id} onChange={(e) => setForm({ ...form, template_id: e.target.value })}>
                <option value="">— Unassigned —</option>
                {templatesForLocation(form.location).map((t) => <option key={t.id} value={t.id}>{t.template_no} · {t.name}</option>)}
              </Select>
              <p className="text-[11px] text-muted-foreground">
                {form.location
                  ? `Showing templates for location "${form.location}". Used whenever no dated assignment (history icon) applies yet.`
                  : 'No location set — showing location-less (general) templates only.'}
              </p>
            </Field>
            <Field label="Bank name">
              <Input value={form.bank_name || ''} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} />
            </Field>
            <Field label="Bank account">
              <Input value={form.bank_account || ''} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} />
            </Field>
            <Field label="IFSC">
              <Input value={form.ifsc || ''} onChange={(e) => setForm({ ...form, ifsc: e.target.value })} />
            </Field>
            <Field label="PAN">
              <Input value={form.pan || ''} onChange={(e) => setForm({ ...form, pan: e.target.value })} />
            </Field>
            <Field label="PF Eligible">
              <Select value={String(form.pf_eligible)} onChange={(e) => setForm({ ...form, pf_eligible: e.target.value === 'true' })}>
                <option value="true">YES</option>
                <option value="false">NO</option>
              </Select>
            </Field>
            <Field label="UAN">
              <Input value={form.uan || ''} onChange={(e) => setForm({ ...form, uan: e.target.value })} />
            </Field>
            <Field label="EPS Eligible">
              <Select value={String(form.eps_eligible)} onChange={(e) => setForm({ ...form, eps_eligible: e.target.value === 'true' })}>
                <option value="true">YES</option>
                <option value="false">NO</option>
              </Select>
            </Field>
            <Field label="ESI Eligible">
              <Select value={String(form.esi_eligible)} onChange={(e) => setForm({ ...form, esi_eligible: e.target.value === 'true' })}>
                <option value="true">YES</option>
                <option value="false">NO</option>
              </Select>
            </Field>
            <Field label="ESI Number">
              <Input value={form.esi_number || ''} onChange={(e) => setForm({ ...form, esi_number: e.target.value })} />
            </Field>
            <Field label="Mediclaim Eligible">
              <Select value={String(form.mediclaim_eligible)} onChange={(e) => setForm({ ...form, mediclaim_eligible: e.target.value === 'true' })}>
                <option value="true">YES</option>
                <option value="false">NO</option>
              </Select>
            </Field>
            <Field label="Mediclaim Policy No.">
              <Input value={form.mediclaim_policy_no || ''} onChange={(e) => setForm({ ...form, mediclaim_policy_no: e.target.value })} />
            </Field>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit">{editing ? 'Save changes' : 'Create employee'}</Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={!!assignEmployee}
        onClose={() => setAssignEmployee(null)}
        title={assignEmployee ? `Template history — ${assignEmployee.employee_code} · ${assignEmployee.first_name} ${assignEmployee.last_name}` : ''}
      >
        {assignEmployee && (
          <div className="space-y-4">
            <Alert>
              A new assignment overrides earlier ones from its effective month onward. E.g. Jan 2026 → Template A,
              Mar 2026 → Template B: payroll for Jan/Feb 2026 uses A, payroll from Mar 2026 uses B, until a later
              assignment (e.g. Mar 2027 → Template C) takes over from that point.
              {assignEmployee.location
                ? ` Showing templates for location "${assignEmployee.location}".`
                : ' This employee has no location set, so only location-less (general) templates are shown.'}
            </Alert>

            {assignError && <Alert variant="destructive">{assignError}</Alert>}

            <form onSubmit={addAssignment} className="flex flex-wrap items-end gap-2">
              <div className="w-52">
                <Label>Template</Label>
                <Select value={assignForm.template_id} onChange={(e) => setAssignForm({ ...assignForm, template_id: e.target.value })} required>
                  <option value="">Select template</option>
                  {templatesForLocation(assignEmployee.location).map((t) => <option key={t.id} value={t.id}>{t.template_no} · {t.name}</option>)}
                </Select>
              </div>
              <div className="w-36">
                <Label>Effective month</Label>
                <Select value={assignForm.effective_month} onChange={(e) => setAssignForm({ ...assignForm, effective_month: e.target.value })}>
                  {MONTH_NAMES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </Select>
              </div>
              <div className="w-24">
                <Label>Year</Label>
                <Input type="number" value={assignForm.effective_year} onChange={(e) => setAssignForm({ ...assignForm, effective_year: e.target.value })} />
              </div>
              <Button type="submit"><Plus className="h-4 w-4" /> Add</Button>
            </form>

            <Table>
              <THead><TR><TH>Effective from</TH><TH>Template</TH><TH></TH></TR></THead>
              <TBody>
                {assignments.map((a) => (
                  <TR key={a.id}>
                    <TD className="font-mono-num">{MONTH_NAMES[a.effective_month - 1]} {a.effective_year}</TD>
                    <TD>{a.template ? `${a.template.template_no} · ${a.template.name}` : a.template_id}</TD>
                    <TD>
                      <Button variant="ghost" size="icon" onClick={() => removeAssignment(a.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TD>
                  </TR>
                ))}
                {assignments.length === 0 && (
                  <TR><TD colSpan={3} className="py-6 text-center text-muted-foreground">
                    No dated assignments yet — the default template above applies to all periods.
                  </TD></TR>
                )}
              </TBody>
            </Table>
          </div>
        )}
      </Dialog>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}
