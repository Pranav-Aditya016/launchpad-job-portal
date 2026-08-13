"use client";

import { motion, useReducedMotion } from "motion/react";
import { scoreTone } from "@/lib/utils";

const TONE_VAR: Record<string, string> = {
  excellent: "var(--success)",
  good: "var(--accent)",
  fair: "var(--warning)",
  poor: "var(--danger)",
};

interface ScoreDialProps {
  score: number;
  size?: number;
  strokeWidth?: number;
}

// A read-only value display, not a gesture — so it settles with a plain
// critically-damped spring (no overshoot) per the apple-design skill's
// guidance that bounce is reserved for momentum the user themselves imparted.
export function ScoreDial({ score, size = 56, strokeWidth = 5 }: ScoreDialProps) {
  const reduceMotion = useReducedMotion();
  const clamped = Math.max(0, Math.min(100, score));
  const tone = scoreTone(clamped);
  const color = TONE_VAR[tone];
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={
            reduceMotion
              ? { duration: 0.2 }
              : { type: "spring", bounce: 0, duration: 0.7 }
          }
        />
      </svg>
      <div
        className="absolute inset-0 flex items-center justify-center text-[0.8125rem] font-bold tabular-nums"
        style={{ color }}
      >
        {Math.round(clamped)}
      </div>
    </div>
  );
}
