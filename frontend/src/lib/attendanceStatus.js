export const STATUS_META = {
  '': { label: '·', className: 'bg-white text-muted-foreground' },
  P: { label: 'P', className: 'bg-emerald-100 text-emerald-800' },
  '2P': { label: '2P', className: 'bg-blue-100 text-blue-800' },
  HD: { label: 'HD', className: 'bg-amber-100 text-amber-800' },
  AB: { label: 'AB', className: 'bg-red-100 text-red-800' },
  EL: { label: 'EL', className: 'bg-purple-100 text-purple-800' },
  WO: { label: 'WO', className: 'bg-slate-100 text-slate-700' },
  R: { label: 'R', className: 'bg-cyan-100 text-cyan-800' },
  S: { label: 'S', className: 'bg-orange-100 text-orange-800' },
}

export const STATUS_OPTIONS = ['', 'P', '2P', 'HD', 'AB', 'EL', 'WO', 'R', 'S']

export const STATUS_LEGEND = [
  ['P', 'Present (1 day)'],
  ['2P', 'Double duty — two days present (e.g. drivers)'],
  ['HD', 'Half day (0.5 day)'],
  ['AB', 'Absent (unpaid, loss of pay)'],
  ['EL', 'Earned leave (paid, drawn from EL balance)'],
  ['WO', 'Week off (paid, does not use EL)'],
  ['R', 'Rest day (unpaid, e.g. drivers — not worked, not paid)'],
  ['S', 'Suspended (separate count, not included in Total/Present)'],
]
