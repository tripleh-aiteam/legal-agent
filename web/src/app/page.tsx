import Link from "next/link";
import { FileSearch, MessageCircle, FilePlus } from "lucide-react";

const MODES = [
  {
    href: "/review",
    icon: FileSearch,
    title: "계약서 검토",
    description:
      "PDF/DOCX 계약서를 업로드하면 AI가 위험 조항을 분석하고, 법률 근거와 함께 수정 제안을 제공합니다.",
    color: "bg-blue-50 text-blue-700 border-blue-200",
  },
  {
    href: "/advise",
    icon: MessageCircle,
    title: "법률 상담",
    description:
      "계약서에 대해 자유롭게 질문하세요. AI가 관련 조항과 법률 근거를 바탕으로 상담해 드립니다.",
    color: "bg-green-50 text-green-700 border-green-200",
  },
  {
    href: "/draft",
    icon: FilePlus,
    title: "계약서 생성",
    description:
      "대화형 인터뷰를 통해 필요한 정보를 수집하고, 맞춤형 계약서를 자동으로 생성합니다.",
    color: "bg-purple-50 text-purple-700 border-purple-200",
  },
];

export default function HomePage() {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="w-full max-w-4xl space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight">
            AI 법률 계약서 에이전트
          </h1>
          <p className="mt-2 text-muted-foreground">
            계약서 검토, 생성, 상담을 위한 AI 어시스턴트
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {MODES.map((mode) => {
            const Icon = mode.icon;
            return (
              <Link
                key={mode.href}
                href={mode.href}
                className={`group rounded-xl border-2 p-6 transition-all hover:shadow-lg ${mode.color}`}
              >
                <Icon className="h-10 w-10" />
                <h2 className="mt-4 text-xl font-semibold">{mode.title}</h2>
                <p className="mt-2 text-sm opacity-80">{mode.description}</p>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
