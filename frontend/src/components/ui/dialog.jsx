import { cn } from '../../lib/utils'
import { X } from 'lucide-react'

export function Dialog({ open, onClose, title, children, className }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className={cn('w-full max-w-lg rounded-lg border border-border bg-card shadow-lg', className)}>
        <div className="flex items-center justify-between border-b border-border p-4">
          <h3 className="font-display text-base font-semibold">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[75vh] overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  )
}
