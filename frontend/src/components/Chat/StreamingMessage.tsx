import { Bot, Loader2 } from "lucide-react"

import type { StreamingState } from "@/hooks/useChatStream"
import { useI18n } from "@/i18n"

import ThinkingBlock from "./ThinkingBlock"
import ToolCallBlock from "./ToolCallBlock"

type StreamingMessageProps = {
  state: StreamingState
}

function BotAvatar() {
  return (
    <span
      aria-hidden
      className="mb-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-border/70 bg-background text-muted-foreground shadow-sm"
    >
      <Bot className="size-3.5" />
    </span>
  )
}

export default function StreamingMessage({ state }: StreamingMessageProps) {
  const { t } = useI18n()
  const { toolCalls, toolResults, thinkingText, contentText, isStreaming } =
    state
  const hasContent = toolCalls.length > 0 || thinkingText || contentText

  if (!hasContent && isStreaming) {
    return (
      <div className="flex items-end gap-2">
        <BotAvatar />
        <div className="mr-auto flex items-center gap-2.5 rounded-2xl rounded-bl-sm border border-dashed border-muted-foreground/30 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          {t("chat.processing")}
        </div>
      </div>
    )
  }

  if (!hasContent) return null

  return (
    <div className="flex min-w-0 items-end gap-2">
      <BotAvatar />
      <div className="mr-auto flex w-full max-w-[85%] min-w-0 flex-col gap-2">
        {toolCalls.map((call, i) => (
          <ToolCallBlock key={i} call={call} result={toolResults[i]} />
        ))}

        {thinkingText && (
          <ThinkingBlock
            text={thinkingText}
            isStreaming={isStreaming && !contentText}
          />
        )}

        {contentText && (
          <div className="min-w-0 rounded-2xl rounded-bl-sm border border-border/70 bg-background px-3.5 py-2.5 text-sm whitespace-pre-wrap break-words shadow-sm">
            {contentText}
            {isStreaming && (
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse rounded-full bg-foreground" />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
