import { Brain } from "lucide-react"
import { useI18n } from "@/i18n"

type ThinkingBlockProps = {
  text: string
  isStreaming?: boolean
}

export default function ThinkingBlock({
  text,
  isStreaming,
}: ThinkingBlockProps) {
  const { t } = useI18n()

  if (!text) return null

  return (
    <details
      open={isStreaming}
      className="group overflow-hidden rounded-lg border border-violet-200 bg-gradient-to-b from-violet-50 to-white shadow-sm dark:border-violet-800 dark:from-violet-950/40 dark:to-background"
    >
      <summary className="flex cursor-pointer items-center gap-2 border-b border-violet-200 bg-violet-100/60 px-3 py-2 dark:border-violet-800 dark:bg-violet-900/30">
        <Brain className="size-3.5 shrink-0 text-violet-600 dark:text-violet-400" />
        <span className="text-xs font-semibold text-violet-800 dark:text-violet-300">
          {t("chat.thinking")}
        </span>
        {isStreaming && (
          <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-medium text-violet-500">
            <span className="inline-block size-1.5 animate-pulse rounded-full bg-violet-500" />
            {t("chat.thinkingStatus")}
          </span>
        )}
      </summary>
      <div className="max-h-64 overflow-auto p-3 text-xs leading-relaxed whitespace-pre-wrap text-violet-900 dark:text-violet-200">
        {text}
      </div>
    </details>
  )
}
