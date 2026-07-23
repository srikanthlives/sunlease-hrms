import { useState } from 'react'
import api from '../api'
import { usePeriod } from '../period/PeriodContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Alert } from '../components/ui/alert'
import { Landmark, Search, Download, Info } from 'lucide-react'
import { MONTH_NAMES, formatCurrency } from '../lib/utils'

function todayDDMMYYYY() {
  const d = new Date()
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
}

export default function BankPayments() {
  const { month, year } = usePeriod()
  const [form, setForm] = useState({
    debit_account_number: '', transaction_date: todayDDMMYYYY(),
    coach_captain_designation: 'Coach Captain', remarks: '',
    generation_mode: 'full_salary',
  })
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function payload() {
    return {
      month, year,
      debit_account_number: form.debit_account_number,
      transaction_date: form.transaction_date,
      coach_captain_designation: form.coach_captain_designation || 'Coach Captain',
      remarks: form.remarks || null,
      generation_mode: form.generation_mode,
    }
  }

  async function doPreview() {
    setError(''); setPreview(null)
    setLoading(true)
    try {
      const { data } = await api.post('/bank-payments/preview', payload())
      setPreview(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to preview')
    } finally {
      setLoading(false)
    }
  }

  async function doDownload() {
    setError('')
    if (!form.debit_account_number) {
      setError('Debit account number is required before generating the file.')
      return
    }
    setLoading(true)
    try {
      const res = await api.post('/bank-payments/download', payload(), { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `BankPayments_${String(month).padStart(2, '0')}${year}.zip`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)

      const ccCount = res.headers['x-cc-count']
      const stCount = res.headers['x-st-count']
      const warningsRaw = res.headers['x-warnings']
      let msg = `Downloaded — Coach Captain file: ${ccCount || 0} row(s), Staff file: ${stCount || 0} row(s).`
      if (warningsRaw) {
        msg += ' Warnings: ' + decodeURIComponent(warningsRaw)
      }
      setPreview({ ...preview, downloadMessage: msg })
    } catch (err) {
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        try {
          setError(JSON.parse(text).detail || 'Failed to generate file')
        } catch {
          setError('Failed to generate file')
        }
      } else {
        setError(err.response?.data?.detail || 'Failed to generate file')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Bank Payments (IDFC FIRST Bank)</h1>
        <p className="text-sm text-muted-foreground">
          Generates IDFC FIRST Bank's bulk NEFT upload format, split into two files by designation — Coach Captain and Staff/Other
          roles — with the outstanding balance (net pay minus anything already recorded via Salary Payments) as the amount.
        </p>
        <p className="text-sm text-muted-foreground mt-2">
          <strong>Generation modes:</strong> Select <em>Full Salary</em> to include all employees with outstanding balance, or
          <em> Pending Payments</em> to include only employees who haven't been fully paid yet.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar — payroll must be run for this period first)</span>
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Generation details</CardTitle>
          <CardDescription>These become the "Debit Account Number" and "Transaction Date" columns in the bank file.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label>Debit account number</Label>
            <Input value={form.debit_account_number} onChange={(e) => setForm({ ...form, debit_account_number: e.target.value })} placeholder="e.g. 73374880882" />
          </div>
          <div className="space-y-1.5">
            <Label>Transaction date (DD/MM/YYYY)</Label>
            <Input value={form.transaction_date} onChange={(e) => setForm({ ...form, transaction_date: e.target.value })} placeholder="08/07/2026" />
          </div>
          <div className="space-y-1.5">
            <Label>"Coach Captain" designation label</Label>
            <Input value={form.coach_captain_designation} onChange={(e) => setForm({ ...form, coach_captain_designation: e.target.value })} />
            <p className="text-[11px] text-muted-foreground">Employees with this exact designation go into the CC file; everyone else goes into the Staff file.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Remarks (optional override)</Label>
            <Input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} placeholder={`Salary for ${MONTH_NAMES[month - 1].slice(0, 3)} - ${year}`} />
          </div>
          <div className="space-y-1.5">
            <Label>Generation mode</Label>
            <div className="flex gap-4 p-3 border rounded-md bg-muted/30">
              <label className="flex items-center space-x-2 cursor-pointer flex-1">
                <input type="radio" name="generation_mode" value="full_salary" checked={form.generation_mode === 'full_salary'} onChange={() => setForm({ ...form, generation_mode: 'full_salary' })} className="accent-primary h-4 w-4" />
                <div>
                  <span className="font-medium text-sm">Full Salary</span>
                  <p className="text-xs text-muted-foreground mt-0.5">Includes all employees with outstanding balance (net pay minus part-payments already recorded).</p>
                </div>
              </label>
              <label className="flex items-center space-x-2 cursor-pointer flex-1">
                <input type="radio" name="generation_mode" value="pending_payments" checked={form.generation_mode === 'pending_payments'} onChange={() => setForm({ ...form, generation_mode: 'pending_payments' })} className="accent-primary h-4 w-4" />
                <div>
                  <span className="font-medium text-sm">Pending Payments Only</span>
                  <p className="text-xs text-muted-foreground mt-0.5">Includes only employees with unpaid or partially paid salary balance (excludes fully paid employees).</p>
                </div>
              </label>
            </div>
            <p className="text-[11px] text-muted-foreground">
              <Info className="h-3 w-3 inline" /> The generated file will only include employees with remaining balance (net pay - payments already made).
            </p>
          </div>
        </CardContent>
        <CardContent className="flex gap-3 pt-0">
          <Button variant="outline" onClick={doPreview} disabled={loading}><Search className="h-4 w-4" /> Preview</Button>
          <Button onClick={doDownload} disabled={loading}><Download className="h-4 w-4" /> Generate & Download</Button>
        </CardContent>
      </Card>

      {error && <Alert variant="destructive">{error}</Alert>}

      {preview && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Summary</CardTitle>
              <span className="text-xs px-2 py-1 rounded bg-muted border">{preview.generation_mode === 'full_salary' ? 'Full Salary' : 'Pending Payments Only'}</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {preview.downloadMessage && <Alert variant="success">{preview.downloadMessage}</Alert>}
            <p className="text-xs text-muted-foreground">
              {preview.generation_mode === 'full_salary'
                ? 'Includes all employees with outstanding balance (net pay minus part-payments already recorded).'
                : 'Includes only employees with unpaid or partially paid salary balance. Fully paid employees are excluded.'}
            </p>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-md border border-border p-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Coach Captain file</p>
                <p className="font-mono-num text-lg font-semibold">{preview.coach_captain_count ?? 0} employee(s)</p>
                <p className="font-mono-num text-primary">₹ {formatCurrency(preview.coach_captain_total ?? 0)}</p>
              </div>
              <div className="rounded-md border border-border p-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Staff file</p>
                <p className="font-mono-num text-lg font-semibold">{preview.staff_count ?? 0} employee(s)</p>
                <p className="font-mono-num text-primary">₹ {formatCurrency(preview.staff_total ?? 0)}</p>
              </div>
            </div>
            {preview.warnings?.length > 0 && (
              <Alert variant="warning">
                <p className="mb-1 font-medium">Warnings:</p>
                {preview.warnings.map((w, i) => <div key={i}>{w}</div>)}
              </Alert>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
