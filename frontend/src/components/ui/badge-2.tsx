import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-rose-500/30 bg-rose-500/15 text-rose-300",
        warning: "border-amber-500/30 bg-amber-500/15 text-amber-300",
        success: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300",
        info: "border-cyan-500/30 bg-cyan-500/15 text-cyan-300",
        outline: "text-foreground border border-input",
      },
      appearance: {
        solid: "border-transparent",
        light: "border backdrop-blur-xs",
        outline: "bg-transparent border",
      },
      size: {
        default: "px-3 py-1 text-xs font-semibold",
        sm: "px-2.5 py-0.5 text-xs font-semibold",
        lg: "px-3.5 py-1.5 text-sm font-semibold",
      },
    },
    defaultVariants: {
      variant: "default",
      appearance: "solid",
      size: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, appearance, size, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant, appearance, size }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
