import { useState } from 'react'
import api from '../api'
import { usePeriod } from '../period/PeriodContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Alert } from '../components/ui/alert'
import { UploadCloud, CalendarDays } from 'lucide-react'
import { MONTH_NAMES } from '../lib/utils'

export default function AttendanceUpload() {
  const { month, year } = usePeriod()

  const [dayDate, setDayDate] = useState(`${year}-${String(month).padStart(2, '0')}-01`)
  const [dayFile, setDayFile] = useState(null)
  const [dayResult, setDayResult] = useState(null)
  const [dayError, setDayError] = useState('')

  const [monthFile, setMonthFile] = useState(null)
  const [monthResult, setMonthResult] = useState(null)
  const [monthError, setMonthError] = useState('')

  async function uploadDay() {
    setDayError(''); setDayResult(null)
    if (!dayFile) return
    const formData = new FormData()
    formData.append('file', dayFile)
    try {
      const { data } = await api.post('/attendance/daily/upload-day', formData, {
        params: { date: dayDate },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setDayResult(data)
    } catch (err) {
      setDayError(err.response?.data?.detail || 'Upload failed')
    }
  }

  async function uploadMonth() {
    setMonthError(''); setMonthResult(null)
    if (!monthFile) return
    const formData = new FormData()
    formData.append('file', monthFile)
    try {
      const { data } = await api.post('/attendance/daily/upload-month', formData, {
        params: { month, year },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setMonthResult(data)
    } catch (err) {
      setMonthError(err.response?.data?.detail || 'Upload failed')
    }
  }

  const daysInSelectedMonth = new Date(year, month, 0).getDate()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Attendance — Bulk Upload</h1>
        <p className="text-sm text-muted-foreground">
          Upload attendance for a single day across many employees, or for a whole month in one file.
          Rows marking a day as <b>EL</b> are rejected (with a clear error, nothing else in the file is affected)
          if the employee doesn't have enough earned-leave balance accrued yet.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground">
        Period: <span className="text-foreground">{MONTH_NAMES[month - 1]} {year}</span>
        <span className="ml-1 text-xs">(change from the top bar)</span>
      </p>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><CalendarDays className="h-4 w-4" /> Upload for a single day</CardTitle>
            <CardDescription>Columns: employee_code, status (P/2P/HD/AB/EL/WO/R), remarks (optional).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input type="date" value={dayDate} onChange={(e) => setDayDate(e.target.value)} />
            <input type="file" accept=".xlsx,.xls" onChange={(e) => setDayFile(e.target.files[0])} className="text-sm" />
            <Button onClick={uploadDay}><UploadCloud className="h-4 w-4" /> Upload</Button>
            {dayError && <Alert variant="destructive">{dayError}</Alert>}
            {dayResult && (
              <>
                <Alert variant="success">Inserted {dayResult.inserted}, updated {dayResult.updated}.</Alert>
                {dayResult.errors.length > 0 && <Alert variant="destructive">{dayResult.errors.map((e, i) => <div key={i}>{e}</div>)}</Alert>}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><UploadCloud className="h-4 w-4" /> Upload for the whole month</CardTitle>
            <CardDescription>
              One row per employee. Columns: employee_code, employee_name (optional, for reference — matching is by
              code), then one column per day — <span className="font-mono-num">1, 2, 3 … {daysInSelectedMonth}</span> for
              {' '}{MONTH_NAMES[month - 1]} {year} — each holding that day's status code. Blank cells are left unmarked.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input type="file" accept=".xlsx,.xls" onChange={(e) => setMonthFile(e.target.files[0])} className="text-sm" />
            <Button onClick={uploadMonth}><UploadCloud className="h-4 w-4" /> Upload</Button>
            {monthError && <Alert variant="destructive">{monthError}</Alert>}
            {monthResult && (
              <>
                <Alert variant="success">Inserted {monthResult.inserted}, updated {monthResult.updated}.</Alert>
                {monthResult.errors.length > 0 && <Alert variant="destructive">{monthResult.errors.map((e, i) => <div key={i}>{e}</div>)}</Alert>}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
