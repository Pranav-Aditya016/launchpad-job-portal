"use client";

import { motion, useReducedMotion } from "motion/react";
import { scoreTone, SCORE_MAX } from "@/lib/utils";

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
  // Score is 1-5 (see SCORE_MAX doc comment in lib/utils.ts) — NOT 0-100.
  const clamped = Math.max(0, Math.min(SCORE_MAX, score));
  const tone = scoreTone(clamped);
  const color = TONE_VAR[tone];
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / SCORE_MAX);

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      title={`${clamped.toFixed(1)} / ${SCORE_MAX}`}
    >
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
        className="absolute inset-0 flex flex-col items-center justify-center leading-none"
        style={{ color }}
      >
        <span className="text-[0.8125rem] font-bold tabular-nums">{clamped.toFixed(1)}</span>
        <span className="text-[0.5rem] font-semibold tabular-nums opacity-70">/{SCORE_MAX}</span>
      </div>
    </div>
  );
}
