import { useEffect, useState } from 'react'
import api from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select } from '../components/ui/select'
import { Badge } from '../components/ui/badge'
import { Alert } from '../components/ui/alert'
import { Table, THead, TBody, TR, TH, TD } from '../components/ui/table'
import { Dialog } from '../components/ui/dialog'
import { Plus, Trash2, Save, FileStack, ArrowUp, ArrowDown, UploadCloud, CopyPlus } from 'lucide-react'
import { formatCurrency } from '../lib/utils'

const BLANK_COMPONENT = () => ({
  code: '', name: '', component_type: 'earning', calculation_type: 'fixed',
  value: 0, formula: '', is_variable: false, default_value: 0,
  prorate_by_attendance: false, sequence: 0, is_active: true,
})

export default function Templates() {
  const [templates, setTemplates] = useState([])
  const [selected, setSelected] = useState(null)
  const [meta, setMeta] = useState({ template_no: '', name: '', description: '', location: '' })
  const [components, setComponents] = useState([])
  const [message, setMessage] = useState(null)
  const [error, setError] = useState('')
  const [bulkFile, setBulkFile] = useState(null)
  const [bulkResult, setBulkResult] = useState(null)
  const [cloneOpen, setCloneOpen] = useState(false)
  const [cloneForm, setCloneForm] = useState({ template_no: '', name: '', location: '' })
  const [cloneError, setCloneError] = useState('')

  function load() {
    api.get('/templates').then((r) => setTemplates(r.data))
  }
  useEffect(load, [])

  // Rough totals shown below the component table while designing a template. Only FIXED
  // values and variable components' default_value are precisely known at design time;
  // PERCENTAGE/FORMULA components depend on other components or attendance, so they're
  // flagged as "varies" rather than guessed at.
  function computeTotals(comps) {
    const totals = { earnings: 0, deductions: 0, employer: 0, hasUnknown: false }
    for (const c of comps) {
      if (c.component_type === 'reference') continue // never money, skip entirely
      let amount = null
      if (c.is_variable) amount = Number(c.default_value) || 0
      else if (c.calculation_type === 'fixed') amount = Number(c.value) || 0
      if (amount === null) {
        totals.hasUnknown = true
        continue
      }
      if (c.component_type === 'earning') totals.earnings += amount
      else if (c.component_type === 'deduction') totals.deductions += amount
      else if (c.component_type === 'employer_contribution') totals.employer += amount
    }
    return totals
  }

  function selectTemplate(t) {
    setSelected(t)
    setMeta({ template_no: t.template_no, name: t.name, description: t.description || '', location: t.location || '' })
    setComponents(t.components.map((c) => ({ ...c })))
    setMessage(null); setError(''); setBulkResult(null)
  }

  function newTemplate() {
    setSelected('new')
    setMeta({ template_no: '', name: '', description: '', location: '' })
    setComponents([])
    setMessage(null); setError('')
  }

  function addComponent() {
    setComponents([...components, { ...BLANK_COMPONENT(), sequence: components.length + 1 }])
  }
  function updateComponent(idx, field, value) {
    const next = [...components]
    next[idx] = { ...next[idx], [field]: value }
    setComponents(next)
  }
  function removeComponent(idx) {
    setComponents(components.filter((_, i) => i !== idx))
  }
  function moveComponent(idx, direction) {
    const target = idx + direction
    if (target < 0 || target >= components.length) return
    const next = [...components]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    setComponents(next)
  }

  async function deleteTemplate() {
    if (!selected || selected === 'new') return
    if (!window.confirm(`Delete template ${selected.template_no} · ${selected.name}? This cannot be undone.`)) return
    setError(''); setMessage(null)
    try {
      await api.delete(`/templates/${selected.id}`)
      setSelected(null)
      setComponents([])
      setMeta({ template_no: '', name: '', description: '', location: '' })
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete template')
    }
  }

  function openClone() {
    if (!selected || selected === 'new') return
    setCloneForm({
      template_no: `${selected.template_no}-COPY`,
      name: `${selected.name} (Copy)`,
      location: selected.location || '',
    })
    setCloneError('')
    setCloneOpen(true)
  }

  async function submitClone(e) {
    e.preventDefault()
    setCloneError('')
    try {
      const { data } = await api.post(`/templates/${selected.id}/clone`, {
        template_no: cloneForm.template_no.trim(),
        name: cloneForm.name.trim(),
        location: cloneForm.location.trim(),
      })
      setCloneOpen(false)
      setMessage(`Cloned as ${data.template_no}.`)
      load()
      selectTemplate(data)
    } catch (err) {
      setCloneError(err.response?.data?.detail || 'Failed to clone template')
    }
  }

  async function uploadComponents() {
    setBulkResult(null)
    if (!bulkFile || selected === 'new' || !selected) return
    const formData = new FormData()
    formData.append('file', bulkFile)
    try {
      const { data } = await api.post(`/templates/${selected.id}/components/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setBulkResult(data)
      if (data.success) {
        const r = await api.get(`/templates/${selected.id}`)
        selectTemplate(r.data)
        load()
      }
    } catch (err) {
      setBulkResult({ success: false, applied: 0, errors: [err.response?.data?.detail || 'Upload failed'] })
    }
  }

  async function save() {
    setError(''); setMessage(null)
    const payload = {
      ...meta,
      components: components.map((c, idx) => ({
        ...c,
        value: Number(c.value) || 0,
        default_value: Number(c.default_value) || 0,
        sequence: idx + 1, // order in the list = order on the payslip
        code: c.code.toUpperCase().trim(),
        formula: c.formula || null,
      })),
    }
    try {
      if (selected === 'new') {
        const { data } = await api.post('/templates', payload)
        setMessage('Template created.')
        load()
        selectTemplate(data)
      } else {
        const { data } = await api.put(`/templates/${selected.id}`, payload)
        setMessage('Template saved.')
        load()
        selectTemplate(data)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save template')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-2xl font-semibold">Salary Templates</h1>
          <p className="text-sm text-muted-foreground">Design salary structures — components can be Earnings, Deductions, Employer Contributions (cost-to-company only), or Reference values (calculation helpers).</p>
        </div>
        <Button onClick={newTemplate} className="shrink-0 whitespace-nowrap"><Plus className="h-4 w-4" /> New template</Button>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <Card className="col-span-3">
          <CardHeader><CardTitle className="text-base">All templates</CardTitle></CardHeader>
          <CardContent className="space-y-2 pt-0">
            {templates.map((t) => (
              <button
                key={t.id}
                onClick={() => selectTemplate(t)}
                className={`flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm ${selected?.id === t.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted'}`}
              >
                <FileStack className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="font-medium font-mono-num">{t.template_no}</p>
                  <p className="text-xs text-muted-foreground">{t.name}</p>
                </div>
              </button>
            ))}
            {templates.length === 0 && <p className="text-sm text-muted-foreground">No templates yet.</p>}
          </CardContent>
        </Card>

        <div className="col-span-9 space-y-4">
          {selected ? (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-4">
                <CardTitle className="text-base">Template details</CardTitle>
                {selected !== 'new' && (
                  <div className="flex shrink-0 gap-2">
                    <Button variant="outline" size="sm" onClick={openClone} className="whitespace-nowrap">
                      <CopyPlus className="h-3.5 w-3.5" /> Clone
                    </Button>
                    <Button variant="outline" size="sm" onClick={deleteTemplate} className="whitespace-nowrap text-destructive hover:bg-destructive/10">
                      <Trash2 className="h-3.5 w-3.5" /> Delete template
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                {error && <Alert variant="destructive">{error}</Alert>}
                {message && <Alert variant="success">{message}</Alert>}
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1.5">
                    <Label>Template No.</Label>
                    <Input value={meta.template_no} onChange={(e) => setMeta({ ...meta, template_no: e.target.value })} placeholder="T-002" />
                  </div>
                  <div className="col-span-2 space-y-1.5">
                    <Label>Name</Label>
                    <Input value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} placeholder="Junior Staff Template" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Location (optional)</Label>
                    <Input value={meta.location} onChange={(e) => setMeta({ ...meta, location: e.target.value })} placeholder="e.g. Mumbai" />
                    <p className="text-[11px] text-muted-foreground">If set, only employees at this location can have this template attached. Leave blank for a general template.</p>
                  </div>
                  <div className="col-span-2 space-y-1.5">
                    <Label>Description</Label>
                    <Input value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <h4 className="font-display text-sm font-semibold">Components</h4>
                  <div className="flex items-center gap-2">
                    {selected !== 'new' && (
                      <>
                        <input
                          type="file" accept=".xlsx,.xls"
                          onChange={(e) => setBulkFile(e.target.files[0])}
                          className="max-w-[180px] text-xs"
                        />
                        <Button size="sm" variant="outline" onClick={uploadComponents}><UploadCloud className="h-3.5 w-3.5" /> Bulk replace</Button>
                      </>
                    )}
                    <Button size="sm" variant="outline" onClick={addComponent}><Plus className="h-3.5 w-3.5" /> Add component</Button>
                  </div>
                </div>

                {bulkResult && (
                  bulkResult.success ? (
                    <Alert variant="success">Replaced components with {bulkResult.applied} row(s) from the file.</Alert>
                  ) : (
                    <Alert variant="destructive">
                      <p className="mb-1 font-medium">Upload rejected — fix these and re-upload (nothing was changed):</p>
                      {bulkResult.errors.map((e, i) => <div key={i}>{e}</div>)}
                    </Alert>
                  )
                )}

                <Table>
                  <THead>
                    <TR>
                      <TH>Code</TH><TH>Name</TH><TH>Type</TH><TH>Calc</TH>
                      <TH>Value / Formula</TH><TH>Variable?</TH><TH>Default</TH><TH>Prorate</TH><TH></TH>
                    </TR>
                  </THead>
                  <TBody>
                    {components.map((c, idx) => (
                      <TR key={idx}>
                        <TD className="min-w-[110px]">
                          <Input value={c.code} onChange={(e) => updateComponent(idx, 'code', e.target.value.toUpperCase())} placeholder="BASIC" />
                        </TD>
                        <TD className="min-w-[150px]">
                          <Input value={c.name} onChange={(e) => updateComponent(idx, 'name', e.target.value)} placeholder="Basic Pay" />
                        </TD>
                        <TD className="min-w-[150px]">
                          <Select value={c.component_type} onChange={(e) => updateComponent(idx, 'component_type', e.target.value)}>
                            <option value="earning">Earning</option>
                            <option value="deduction">Deduction</option>
                            <option value="employer_contribution">Employer contribution (hidden from payslip)</option>
                            <option value="reference">Reference / notional (calc only, never shown)</option>
                          </Select>
                        </TD>
                        <TD className="min-w-[120px]">
                          <Select value={c.calculation_type} onChange={(e) => updateComponent(idx, 'calculation_type', e.target.value)} disabled={c.is_variable}>
                            <option value="fixed">Fixed</option>
                            <option value="percentage">% of component</option>
                            <option value="formula">Formula</option>
                          </Select>
                        </TD>
                        <TD className="min-w-[180px]">
                          {c.is_variable ? (
                            <span className="text-xs text-muted-foreground">Set via monthly upload</span>
                          ) : c.calculation_type === 'fixed' ? (
                            <Input type="number" value={c.value} onChange={(e) => updateComponent(idx, 'value', e.target.value)} />
                          ) : c.calculation_type === 'percentage' ? (
                            <div className="flex gap-1">
                              <Input type="number" className="w-16" value={c.value} onChange={(e) => updateComponent(idx, 'value', e.target.value)} />
                              <Input placeholder="of BASIC + DA" value={c.formula || ''} onChange={(e) => updateComponent(idx, 'formula', e.target.value)} />
                            </div>
                          ) : (
                            <Input placeholder="BASIC + HRA * 0.1" value={c.formula || ''} onChange={(e) => updateComponent(idx, 'formula', e.target.value)} />
                          )}
                        </TD>
                        <TD>
                          <input type="checkbox" checked={c.is_variable} onChange={(e) => updateComponent(idx, 'is_variable', e.target.checked)} />
                        </TD>
                        <TD className="min-w-[90px]">
                          {c.is_variable && <Input type="number" value={c.default_value} onChange={(e) => updateComponent(idx, 'default_value', e.target.value)} />}
                        </TD>
                        <TD>
                          <input type="checkbox" checked={c.prorate_by_attendance} onChange={(e) => updateComponent(idx, 'prorate_by_attendance', e.target.checked)} />
                        </TD>
                        <TD>
                          <div className="flex items-center gap-0.5">
                            <Button variant="ghost" size="icon" disabled={idx === 0} onClick={() => moveComponent(idx, -1)} title="Move up">
                              <ArrowUp className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" disabled={idx === components.length - 1} onClick={() => moveComponent(idx, 1)} title="Move down">
                              <ArrowDown className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" onClick={() => removeComponent(idx)} title="Remove">
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </TD>
                      </TR>
                    ))}
                    {components.length === 0 && (
                      <TR><TD colSpan={9} className="py-6 text-center text-muted-foreground">No components yet — add one above.</TD></TR>
                    )}
                  </TBody>
                </Table>

                {components.length > 0 && (() => {
                  const totals = computeTotals(components)
                  const net = totals.earnings - totals.deductions
                  return (
                    <div className="rounded-md border border-border bg-secondary/40 p-4 text-sm">
                      <p className="mb-2 font-display text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Totals (fixed values &amp; variable defaults only)
                      </p>
                      <div className="space-y-1.5">
                        <div className="flex justify-between">
                          <span>Total earnings</span>
                          <span className="font-mono-num">₹ {formatCurrency(totals.earnings)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Total deductions</span>
                          <span className="font-mono-num">₹ {formatCurrency(totals.deductions)}</span>
                        </div>
                        <div className="flex justify-between border-t border-border pt-1.5 font-semibold">
                          <span>Estimated net pay</span>
                          <span className="font-mono-num">₹ {formatCurrency(net)}</span>
                        </div>
                        {totals.employer > 0 && (
                          <div className="flex justify-between text-amber-700">
                            <span>Employer contribution (cost only)</span>
                            <span className="font-mono-num">₹ {formatCurrency(totals.employer)}</span>
                          </div>
                        )}
                      </div>
                      {totals.hasUnknown && (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Some components use % or formulas that depend on other values or attendance — these totals will differ once payroll actually runs.
                        </p>
                      )}
                    </div>
                  )
                })()}

                <div className="flex justify-end">
                  <Button onClick={save}><Save className="h-4 w-4" /> Save template</Button>
                </div>

                <Alert className="space-y-2">
                  <p>
                    <b>Formula tips:</b> reference other component codes (e.g. <code className="font-mono-num">BASIC + HRA</code>) or attendance
                    variables <code className="font-mono-num">TOTAL_DAYS</code>, <code className="font-mono-num">PRESENT_DAYS</code>, <code className="font-mono-num">LOP_DAYS</code>, <code className="font-mono-num">ATTENDANCE_RATIO</code>.
                    Available functions: <code className="font-mono-num">min()</code>, <code className="font-mono-num">max()</code>, <code className="font-mono-num">round()</code>, <code className="font-mono-num">abs()</code>, <code className="font-mono-num">roundup()</code>, <code className="font-mono-num">rounddown()</code>, <code className="font-mono-num">ceil()</code>, <code className="font-mono-num">floor()</code>,
                    plus comparisons and a ternary <code className="font-mono-num">a if cond else b</code>.
                  </p>
                  <p>
                    <b>% of component</b> now accepts a full expression as the base too, not just one code — e.g. HRA = 40% <code className="font-mono-num">of BASIC + DA</code>.
                  </p>
                  <p>
                    <b>Capped PF example:</b> <code className="font-mono-num">min(BASIC + DA, 15000) * 0.12</code> &nbsp;·&nbsp;
                    <b>Rounded-up allowance:</b> <code className="font-mono-num">roundup(BASIC * 0.05, 10)</code>
                  </p>
                  <p>
                    <b>Employer Contribution</b> components (e.g. Employer PF) are costs to the company only — resolved and totalled into
                    a separate CTC figure, but never shown on the employee's payslip.
                  </p>
                  <p>
                    <b>Reference</b> components are calculation helpers only — e.g. <code className="font-mono-num">GROSS_SALARY = BASIC + DA + HRA</code> — never
                    paid, never shown anywhere, but usable by other formulas (like an ESIC eligibility check: <code className="font-mono-num">GROSS_SALARY &lt;= 21000</code>).
                  </p>
                  <p>
                    Mark a component <b>Variable</b> when its monthly value (e.g. Performance Bonus) needs manual entry / Excel upload each month —
                    the default value applies unless overridden for that employee that month.
                  </p>
                  <p>
                    <b>Bulk replace</b> (Excel) columns: <code className="font-mono-num">code, name, component_type, calculation_type, value, formula, is_variable, default_value, prorate_by_attendance, sequence</code>.
                    Every row is validated first — if anything's wrong, nothing is changed and you'll see the exact row-level errors to fix.
                  </p>
                </Alert>
              </CardContent>
            </Card>
          ) : (
            <Card><CardContent className="py-16 text-center text-muted-foreground">Select a template or create a new one.</CardContent></Card>
          )}
        </div>
      </div>

      <Dialog open={cloneOpen} onClose={() => setCloneOpen(false)} title={selected && selected !== 'new' ? `Clone ${selected.template_no}` : 'Clone template'}>
        {selected && selected !== 'new' && (
          <form onSubmit={submitClone} className="space-y-4">
            {cloneError && <Alert variant="destructive">{cloneError}</Alert>}
            <p className="text-sm text-muted-foreground">
              Copies all {components.length} component(s) from <b>{selected.template_no} · {selected.name}</b> into a new template.
            </p>
            <div className="space-y-1.5">
              <Label>New template no.</Label>
              <Input value={cloneForm.template_no} onChange={(e) => setCloneForm({ ...cloneForm, template_no: e.target.value })} required />
            </div>
            <div className="space-y-1.5">
              <Label>New name</Label>
              <Input value={cloneForm.name} onChange={(e) => setCloneForm({ ...cloneForm, name: e.target.value })} required />
            </div>
            <div className="space-y-1.5">
              <Label>Location (optional)</Label>
              <Input value={cloneForm.location} onChange={(e) => setCloneForm({ ...cloneForm, location: e.target.value })} placeholder="e.g. Mumbai" />
              <p className="text-[11px] text-muted-foreground">Prefilled from the source template — change or clear it for the clone if needed.</p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setCloneOpen(false)}>Cancel</Button>
              <Button type="submit"><CopyPlus className="h-4 w-4" /> Create clone</Button>
            </div>
          </form>
        )}
      </Dialog>
    </div>
  )
}
