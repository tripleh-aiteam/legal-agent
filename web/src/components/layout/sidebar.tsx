"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  FileSearch,
  FilePlus,
  MessageCircle,
  Scale,
} from "lucide-react";

const NAV_ITEMS = [
  {
    href: "/review",
    label: "계약서 검토",
    description: "위험 조항 분석",
    icon: FileSearch,
  },
  {
    href: "/advise",
    label: "법률 상담",
    description: "AI 법률 상담",
    icon: MessageCircle,
  },
  {
    href: "/draft",
    label: "계약서 생성",
    description: "맞춤 계약서 작성",
    icon: FilePlus,
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-64 flex-col border-r bg-card">
      {/* Logo */}
      <Link href="/" className="flex items-center gap-2 border-b px-5 py-4">
        <Scale className="h-6 w-6 text-primary" />
        <span className="text-lg font-bold">Legal Agent</span>
      </Link>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <div>
                <div className="font-medium">{item.label}</div>
                <div
                  className={cn(
                    "text-xs",
                    active ? "text-primary-foreground/70" : "text-muted-foreground",
                  )}
                >
                  {item.description}
                </div>
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t p-4 text-xs text-muted-foreground">
        AI가 제공하는 참고 정보이며,
        <br />
        법률 자문이 아닙니다.
      </div>
    </aside>
  );
}
