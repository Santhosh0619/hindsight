import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-accent text-accent-foreground",
        muted: "border-transparent bg-muted text-muted-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        warning: "border-transparent bg-warning text-warning-foreground",
        success: "border-transparent bg-success text-success-foreground",
        outline: "border-border text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps): React.JSX.Element {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

// badgeVariants is exported alongside Badge so callers can compose the same classes
// without a re-render round-trip (e.g. on an <a> styled as a badge) — standard
// shadcn/ui pattern, at the cost of this file no longer being fast-refresh-only-safe.
// eslint-disable-next-line react-refresh/only-export-components
export { Badge, badgeVariants };
