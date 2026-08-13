"use client";

import { motion, type HTMLMotionProps } from "motion/react";
import { forwardRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "lg" | "sm";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-foreground shadow-[0_1px_2px_rgba(0,0,0,0.12)] hover:brightness-[1.06] disabled:opacity-40",
  secondary:
    "bg-surface-2 text-foreground border border-[color:var(--border-strong)] hover:bg-[color:var(--border)] disabled:opacity-40",
  ghost:
    "bg-transparent text-foreground hover:bg-[color:var(--border)] disabled:opacity-40",
  danger:
    "bg-danger text-white hover:brightness-[1.06] disabled:opacity-40",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "text-[0.8125rem] px-3 py-1.5 rounded-lg gap-1.5",
  md: "text-[0.9375rem] px-4 py-2.5 rounded-xl gap-2",
  lg: "text-[1.0625rem] px-6 py-3.5 rounded-2xl gap-2",
};

interface ButtonProps extends Omit<HTMLMotionProps<"button">, "ref" | "children"> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children?: ReactNode;
}

// Springs, not fixed-duration easing: whileTap fires on pointer-down (not
// release) so the press feels instant, and a critically-damped spring
// (bounce 0) settles it back without overshoot — see apple-design skill §1/§4.
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => {
    return (
      <motion.button
        ref={ref}
        whileTap={{ scale: 0.97 }}
        transition={{ type: "spring", bounce: 0, duration: 0.28 }}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center font-medium select-none",
          "transition-colors duration-150",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className
        )}
        {...props}
      >
        {loading && (
          <span
            aria-hidden
            className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"
          />
        )}
        {children}
      </motion.button>
    );
  }
);
Button.displayName = "Button";
