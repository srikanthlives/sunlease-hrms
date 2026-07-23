import { cn } from '../../lib/utils'

export function Table({ className, ...props }) {
  return (
    <div className="w-full overflow-auto rounded-md border border-border">
      <table className={cn('w-full text-sm', className)} {...props} />
    </div>
  )
}
export function THead({ className, ...props }) {
  return <thead className={cn('bg-secondary/60 text-left', className)} {...props} />
}
export function TBody({ className, ...props }) {
  return <tbody className={cn('divide-y divide-border', className)} {...props} />
}
export function TR({ className, ...props }) {
  return <tr className={cn('hover:bg-muted/50 transition-colors', className)} {...props} />
}
export function TH({ className, ...props }) {
  return <th className={cn('px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground', className)} {...props} />
}
export function TD({ className, ...props }) {
  return <td className={cn('px-4 py-2.5', className)} {...props} />
}
