"use client";

import { useState, useRef, useEffect } from "react";
import { MessageBubble } from "@/components/shared/message-bubble";
import { AdviceCard } from "./advice-card";
import { Send } from "lucide-react";
import type { ChatMessage } from "@/hooks/use-advise";

interface AdviseChatProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onSend: (text: string) => void;
}

export function AdviseChat({ messages, isLoading, onSend }: AdviseChatProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    onSend(text);
  };

  const handleFollowUp = (question: string) => {
    if (isLoading) return;
    onSend(question);
  };

  return (
    <div className="flex h-full flex-col">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <p>계약서에 대해 질문해보세요</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} role={msg.role}>
            {msg.role === "assistant" && msg.advice?.advice ? (
              <AdviceCard data={msg.advice} />
            ) : (
              <p>{msg.content}</p>
            )}
            {/* Follow-up questions */}
            {msg.role === "assistant" &&
              msg.advice?.advice?.follow_up_questions?.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {msg.advice.advice.follow_up_questions.map((q, qi) => (
                  <button
                    key={qi}
                    onClick={() => handleFollowUp(q)}
                    className="rounded-full border bg-background px-3 py-1 text-xs text-foreground hover:bg-accent transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            ) : null}
          </MessageBubble>
        ))}
        {isLoading && (
          <MessageBubble role="assistant">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 animate-bounce rounded-full bg-current" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:0.2s]" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:0.4s]" />
            </div>
          </MessageBubble>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="질문을 입력하세요..."
            className="flex-1 rounded-lg border bg-background px-4 py-2.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="rounded-lg bg-primary px-4 py-2.5 text-primary-foreground disabled:opacity-50 hover:bg-primary/90 transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
