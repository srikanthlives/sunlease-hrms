import { cn } from '../../lib/utils'

export function Alert({ className, variant = 'default', ...props }) {
  const variants = {
    default: 'bg-secondary/60 border-border text-foreground',
    destructive: 'bg-red-50 border-red-200 text-red-800',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
  }
  return <div className={cn('rounded-md border px-4 py-3 text-sm', variants[variant], className)} {...props} />
}
