import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-slate-900 text-white',
        secondary: 'border-transparent bg-slate-100 text-slate-900',
        destructive: 'border-transparent bg-red-600 text-white',
        outline: 'text-slate-900',
        success: 'border-transparent bg-green-100 text-green-800 border-green-200',
        warning: 'border-transparent bg-yellow-100 text-yellow-800 border-yellow-200',
        danger: 'border-transparent bg-orange-100 text-orange-800 border-orange-200',
        info: 'border-transparent bg-blue-100 text-blue-800 border-blue-200',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
