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
import { UploadCloud, Plus, Trash2 } from 'lucide-react'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'

export default function SalaryPayments() {
  const { month, year } = usePeriod()
  const filters = useEmployeeFilters()
  const [employees, setEmployees] = useState([])
  const [payments, setPayments] = useState([])
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [manual, setManual] = useState({ employee_id: '', amount: '', transaction_id: '', payment_date: '', remarks: '' })

  function load() {
    api.get('/employees').then((r) => setEmployees(r.data))
    api.get('/payments', { params: { month, year } }).then((r) => setPayments(r.data))
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
  const displayedPayments = applyEmployeeFilters(payments, filters, (p) => employeeOf(p.employee_id))
  const filtersActive = filters.sortBy !== 'default' || filters.deptFilter || filters.locFilter

  async function uploadFile() {
    setError(''); setResult(null)
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const { data } = await api.post('/payments/upload', formData, {
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
      await api.post('/payments', {
        employee_id: Number(manual.employee_id), month, year, amount: Number(manual.amount),
        transaction_id: manual.transaction_id || null, payment_date: manual.payment_date || null,
        remarks: manual.remarks || null,
      })
      setManual({ employee_id: '', amount: '', transaction_id: '', payment_date: '', remarks: '' })
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save')
    }
  }

  async function removePayment(id) {
    if (!window.confirm('Delete this payment record? The balance shown on the payslip will update accordingly.')) return
    await api.delete(`/payments/${id}`)
    load()
  }

  const totalPaid = payments.reduce((sum, p) => sum + p.amount, 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Salary Payments</h1>
        <p className="text-sm text-muted-foreground">
          Record actual payments made towards this month's salary — can be split across multiple part-payments with
          their own transaction IDs. Each payslip shows these transactions plus the remaining balance, if any.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar)</span>
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Bulk upload (Excel)</CardTitle>
          <CardDescription>Columns: employee_code, amount, transaction_id (optional), payment_date (optional), remarks (optional).</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <input type="file" accept=".xlsx,.xls" onChange={(e) => setFile(e.target.files[0])} className="text-sm" />
          <Button onClick={uploadFile}><UploadCloud className="h-4 w-4" /> Upload</Button>
        </CardContent>
        {error && <CardContent className="pt-0"><Alert variant="destructive">{error}</Alert></CardContent>}
        {result && (
          <CardContent className="pt-0">
            <Alert variant="success">Recorded {result.inserted} payment(s).</Alert>
            {result.errors.length > 0 && (
              <Alert variant="destructive" className="mt-2">
                {result.errors.map((e, i) => <div key={i}>{e}</div>)}
              </Alert>
            )}
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Record a single payment</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={addManual} className="flex flex-wrap items-end gap-3">
            <div className="w-64">
              <Select value={manual.employee_id} onChange={(e) => setManual({ ...manual, employee_id: e.target.value })} required>
                <option value="">Select employee</option>
                {displayedEmployeeOptions.map((e) => <option key={e.id} value={e.id}>{e.employee_code} · {e.first_name} {e.last_name}</option>)}
              </Select>
            </div>
            <Input className="w-32" type="number" placeholder="Amount" value={manual.amount} onChange={(e) => setManual({ ...manual, amount: e.target.value })} required />
            <Input className="w-40" placeholder="Transaction ID" value={manual.transaction_id} onChange={(e) => setManual({ ...manual, transaction_id: e.target.value })} />
            <Input className="w-40" type="date" value={manual.payment_date} onChange={(e) => setManual({ ...manual, payment_date: e.target.value })} />
            <Input className="w-56" placeholder="Remarks (optional)" value={manual.remarks} onChange={(e) => setManual({ ...manual, remarks: e.target.value })} />
            <Button type="submit"><Plus className="h-4 w-4" /> Add payment</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Payments — {MONTH_NAMES[month - 1]} {year}</CardTitle>
          <CardDescription>
            {displayedPayments.length} of {payments.length} payment(s) · ₹ {formatCurrency(totalPaid)} total
            {filtersActive && ' · filtered/sorted via the "Employee filters" bar above'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <THead><TR><TH>Employee</TH><TH>Amount</TH><TH>Transaction ID</TH><TH>Date</TH><TH>Remarks</TH><TH></TH></TR></THead>
            <TBody>
              {displayedPayments.map((p) => (
                <TR key={p.id}>
                  <TD>{employeeLabel(p.employee_id)}</TD>
                  <TD className="font-mono-num">₹ {formatCurrency(p.amount)}</TD>
                  <TD className="font-mono-num text-muted-foreground">{p.transaction_id || '—'}</TD>
                  <TD className="font-mono-num text-muted-foreground">{p.payment_date || '—'}</TD>
                  <TD className="text-muted-foreground">{p.remarks || '—'}</TD>
                  <TD><Button variant="ghost" size="icon" onClick={() => removePayment(p.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button></TD>
                </TR>
              ))}
              {payments.length === 0 && (
                <TR><TD colSpan={6} className="py-6 text-center text-muted-foreground">No payments recorded for this month yet.</TD></TR>
              )}
              {payments.length > 0 && displayedPayments.length === 0 && (
                <TR><TD colSpan={6} className="py-6 text-center text-muted-foreground">No payments match the current filters.</TD></TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
