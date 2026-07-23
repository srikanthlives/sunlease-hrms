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
import { Plus, Trash2 } from 'lucide-react'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'

export default function AdhocEntries() {
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const [employees, setEmployees] = useState([])
  const [entries, setEntries] = useState([])
  const [error, setError] = useState('')
  const [form, setForm] = useState({ employee_id: '', label: '', amount: '', entry_type: 'deduction', remarks: '' })

  function load() {
    api.get('/employees').then((r) => setEmployees(r.data))
    api.get('/adhoc-entries', { params: { month, year } }).then((r) => setEntries(r.data))
  }
  useEffect(load, [month, year])

  function employeeOf(id) {
    return employees.find((x) => x.id === id)
  }
  function employeeLabel(id) {
    const e = employeeOf(id)
    return e ? `${e.employee_code} · ${e.first_name} ${e.last_name}` : id
  }

  const displayedEmployeeOptions = applyEmployeeFilters(employees, filters, (e) => e)
  const displayedEntries = applyEmployeeFilters(entries, filters, (en) => employeeOf(en.employee_id))
  const filtersActive = filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter

  async function submit(e) {
    e.preventDefault()
    setError('')
    try {
      await api.post('/adhoc-entries', {
        employee_id: Number(form.employee_id), month, year,
        label: form.label, amount: Number(form.amount), entry_type: form.entry_type,
        remarks: form.remarks || null,
      })
      setForm({ employee_id: '', label: '', amount: '', entry_type: 'deduction', remarks: '' })
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save')
    }
  }

  async function remove(id) {
    await api.delete(`/adhoc-entries/${id}`)
    load()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Ad-hoc Entries</h1>
        <p className="text-sm text-muted-foreground">
          One-off manual earnings or deductions for a specific employee & month — e.g. a uniform deduction when an employee resigns.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar)</span>
      </p>

      <Card>
        <CardHeader><CardTitle className="text-base">Add entry</CardTitle></CardHeader>
        <CardContent>
          {error && <Alert variant="destructive" className="mb-3">{error}</Alert>}
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <div className="w-64">
              <Select value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} required>
                <option value="">Select employee</option>
                {displayedEmployeeOptions.map((e) => <option key={e.id} value={e.id}>{e.employee_code} · {e.first_name} {e.last_name}</option>)}
              </Select>
            </div>
            <Select className="w-36" value={form.entry_type} onChange={(e) => setForm({ ...form, entry_type: e.target.value })}>
              <option value="deduction">Deduction</option>
              <option value="earning">Earning</option>
            </Select>
            <Input className="w-48" placeholder="Label (e.g. Uniform deduction)" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required />
            <Input className="w-32" type="number" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required />
            <Input className="w-56" placeholder="Remarks (optional)" value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
            <Button type="submit"><Plus className="h-4 w-4" /> Add</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Entries — {MONTH_NAMES[month - 1]} {year}</CardTitle>
          <CardDescription>
            {displayedEntries.length} of {entries.length} entries
            {filtersActive && ' · filtered/sorted via the "Employee filters" bar above'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <THead><TR><TH>Employee</TH><TH>Type</TH><TH>Label</TH><TH>Amount</TH><TH>Remarks</TH><TH></TH></TR></THead>
            <TBody>
              {displayedEntries.map((en) => (
                <TR key={en.id}>
                  <TD>{employeeLabel(en.employee_id)}</TD>
                  <TD><Badge variant={en.entry_type === 'deduction' ? 'destructive' : 'success'}>{en.entry_type}</Badge></TD>
                  <TD>{en.label}</TD>
                  <TD className="font-mono-num">₹ {formatCurrency(en.amount)}</TD>
                  <TD className="text-muted-foreground">{en.remarks || '—'}</TD>
                  <TD><Button variant="ghost" size="icon" onClick={() => remove(en.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button></TD>
                </TR>
              ))}
              {entries.length === 0 && (
                <TR><TD colSpan={6} className="py-6 text-center text-muted-foreground">No ad-hoc entries for this month.</TD></TR>
              )}
              {entries.length > 0 && displayedEntries.length === 0 && (
                <TR><TD colSpan={6} className="py-6 text-center text-muted-foreground">No entries match the current filters.</TD></TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
