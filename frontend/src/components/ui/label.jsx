import { cn } from '../../lib/utils'

export function Label({ className, ...props }) {
  return <label className={cn('text-xs font-medium text-muted-foreground', className)} {...props} />
}
