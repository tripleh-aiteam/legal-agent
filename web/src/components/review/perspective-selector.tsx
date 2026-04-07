"use client";

import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "갑" as const, label: "갑 (발주자)", desc: "갑 입장에서 검토" },
  { value: "을" as const, label: "을 (수급자)", desc: "을 입장에서 검토" },
  { value: "neutral" as const, label: "중립", desc: "양측 균형 검토" },
];

interface PerspectiveSelectorProps {
  value: "갑" | "을" | "neutral";
  onChange: (v: "갑" | "을" | "neutral") => void;
}

export function PerspectiveSelector({ value, onChange }: PerspectiveSelectorProps) {
  return (
    <div className="flex gap-2">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "flex-1 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
            value === opt.value
              ? "border-primary bg-primary/5 text-primary"
              : "border-border hover:border-primary/30",
          )}
        >
          <div className="font-medium">{opt.label}</div>
          <div className="text-xs text-muted-foreground">{opt.desc}</div>
        </button>
      ))}
    </div>
  );
}
