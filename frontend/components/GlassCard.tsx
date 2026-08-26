import type { ElementType, HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GlassCardProps extends HTMLAttributes<HTMLElement> {
  as?: ElementType;
  children: ReactNode;
  className?: string;
  innerClassName?: string;
  hover?: boolean;
  /** Drop the default p-6 inner padding so innerClassName fully controls it
   *  (e.g. an edge-to-edge iframe) — avoids two padding utilities competing
   *  at equal specificity. */
  noPadding?: boolean;
}

// The standard glass-card recipe: an outer .glass shell (blur + border +
// shadow) with a thin frosted rim, and an inner .glass-scrim that carries
// almost the full card so body text always sits on the contrast-safe scrim,
// never directly on .glass — see globals.css's contrast note.
export function GlassCard({
  as: Tag = "div",
  children,
  className,
  innerClassName,
  hover = false,
  noPadding = false,
  ...rest
}: GlassCardProps) {
  return (
    <Tag className={cn("glass p-1.5", hover && "glass-hover", className)} {...rest}>
      <div className={cn("glass-scrim h-full", !noPadding && "p-6", innerClassName)}>
        {children}
      </div>
    </Tag>
  );
}
