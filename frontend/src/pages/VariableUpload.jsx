import { useEffect, useState } from 'react'
import api from '../api'
import { usePeriod } from '../period/PeriodContext'
import { useEmployeeFilters, applyEmployeeFilters } from '../period/EmployeeFilterContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Select } from '../components/ui/select'
import { Alert } from '../components/ui/alert'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { Badge } from '../components/ui/badge'
import { UploadCloud, Plus, Trash2 } from 'lucide-react'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'

export default function VariableUpload() {
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const [employees, setEmployees] = useState([])
  const [overrides, setOverrides] = useState([])
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [manual, setManual] = useState({ employee_id: '', component_code: '', value: '', remarks: '' })

  function load() {
    api.get('/employees').then((r) => setEmployees(r.data))
    api.get('/variable-inputs', { params: { month, year } }).then((r) => setOverrides(r.data))
  }
  useEffect(load, [month, year])

  async function uploadFile() {
    setError(''); setResult(null)
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const { data } = await api.post('/variable-inputs/upload', formData, {
        params: { month, year },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResult(data)
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    }
  }

  async function addManual(e) {
    e.preventDefault()
    setError('')
    try {
      await api.post('/variable-inputs', {
        employee_id: Number(manual.employee_id), component_code: manual.component_code.toUpperCase(),
        month, year, value: Number(manual.value), remarks: manual.remarks || null,
      })
      setManual({ employee_id: '', component_code: '', value: '', remarks: '' })
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save')
    }
  }

  async function removeOverride(id) {
    if (!window.confirm('Delete this override? The template default will apply again for that employee/month.')) return
    try {
      await api.delete(`/variable-inputs/${id}`)
      load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete override')
    }
  }

  function employeeLabel(id) {
    const e = employees.find((x) => x.id === id)
    return e ? `${e.employee_code} · ${e.first_name} ${e.last_name}` : id
  }

  const selectedEmployee = employees.find((e) => String(e.id) === String(manual.employee_id))
  const variableComponents = selectedEmployee?.template?.components?.filter((c) => c.is_variable) || []

  const displayedEmployeeOptions = applyEmployeeFilters(employees, filters, (e) => e)
  const displayedOverrides = applyEmployeeFilters(overrides, filters, (o) => employees.find((e) => e.id === o.employee_id))
  const filtersActive = filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Monthly Variable Components</h1>
        <p className="text-sm text-muted-foreground">
          Override any component marked "variable" for this employee & month — e.g. Performance Bonus defaults to ₹2,000
          but can be overridden to ₹1,500 for a specific employee this month only.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar)</span>
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Bulk upload (Excel)</CardTitle>
          <CardDescription>Columns: employee_code, component_code, value, remarks (optional). Uploaded values override the template default for that employee/month only.</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <input type="file" accept=".xlsx,.xls" onChange={(e) => setFile(e.target.files[0])} className="text-sm" />
          <Button onClick={uploadFile}><UploadCloud className="h-4 w-4" /> Upload</Button>
        </CardContent>
        {error && <CardContent className="pt-0"><Alert variant="destructive">{error}</Alert></CardContent>}
        {result && (
          <CardContent className="pt-0">
            <Alert variant="success">Inserted {result.inserted}, updated {result.updated}.</Alert>
            {result.errors.length > 0 && (
              <Alert variant="destructive" className="mt-2">
                {result.errors.map((e, i) => <div key={i}>{e}</div>)}
              </Alert>
            )}
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Add a single override</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={addManual} className="flex flex-wrap items-end gap-3">
            <div className="w-64">
              <Select
                value={manual.employee_id}
                onChange={(e) => setManual({ ...manual, employee_id: e.target.value, component_code: '' })}
                required
              >
                <option value="">Select employee</option>
                {displayedEmployeeOptions.map((e) => <option key={e.id} value={e.id}>{e.employee_code} · {e.first_name} {e.last_name}</option>)}
              </Select>
            </div>
            <div className="w-64">
              <Select
                value={manual.component_code}
                onChange={(e) => setManual({ ...manual, component_code: e.target.value })}
                disabled={!manual.employee_id || variableComponents.length === 0}
                required
              >
                <option value="">
                  {!manual.employee_id ? 'Select employee first' : variableComponents.length === 0 ? 'No variable components on this template' : 'Select component'}
                </option>
                {variableComponents.map((c) => (
                  <option key={c.code} value={c.code}>{c.code} — {c.name} (default ₹{formatCurrency(c.default_value)})</option>
                ))}
              </Select>
            </div>
            <Input className="w-32" type="number" placeholder="Value" value={manual.value} onChange={(e) => setManual({ ...manual, value: e.target.value })} required />
            <Input className="w-56" placeholder="Remarks (optional)" value={manual.remarks} onChange={(e) => setManual({ ...manual, remarks: e.target.value })} />
            <Button type="submit"><Plus className="h-4 w-4" /> Add override</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Active overrides — {MONTH_NAMES[month - 1]} {year}</CardTitle>
          <CardDescription>
            {displayedOverrides.length} of {overrides.length} override(s)
            {filtersActive && ' · filtered/sorted via the "Employee filters" bar above'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <THead><TR><TH>Employee</TH><TH>Component</TH><TH>Value</TH><TH>Remarks</TH><TH>Uploaded by</TH><TH></TH></TR></THead>
            <TBody>
              {displayedOverrides.map((o) => (
                <TR key={o.id}>
                  <TD>{employeeLabel(o.employee_id)}</TD>
                  <TD><Badge variant="default">{o.component_code}</Badge></TD>
                  <TD className="font-mono-num">₹ {formatCurrency(o.value)}</TD>
                  <TD className="text-muted-foreground">{o.remarks || '—'}</TD>
                  <TD className="text-muted-foreground">{o.uploaded_by || '—'}</TD>
                  <TD>
                    <Button variant="ghost" size="icon" onClick={() => removeOverride(o.id)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </TD>
                </TR>
              ))}
              {overrides.length === 0 && (
                <TR><TD colSpan={6} className="py-6 text-center text-muted-foreground">No overrides for this month yet — defaults from the template will apply.</TD></TR>
              )}
              {overrides.length > 0 && displayedOverrides.length === 0 && (
                <TR><TD colSpan={6} className="py-6 text-center text-muted-foreground">No overrides match the current filters.</TD></TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
