import { CheckCircle2, Loader2, Terminal } from "lucide-react"

import type { ToolCallEvent, ToolResultEvent } from "@/hooks/useChatStream"
import { useI18n } from "@/i18n"

type ToolCallBlockProps = {
  call: ToolCallEvent
  result?: ToolResultEvent
}

export default function ToolCallBlock({ call, result }: ToolCallBlockProps) {
  const isLoading = !result
  const { t } = useI18n()

  return (
    <div className="overflow-hidden rounded-lg border border-sky-200 bg-gradient-to-b from-sky-50 to-white shadow-sm dark:border-sky-800 dark:from-sky-950/40 dark:to-background">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-sky-200 bg-sky-100/60 px-3 py-2 dark:border-sky-800 dark:bg-sky-900/30">
        {isLoading ? (
          <Loader2 className="size-3.5 shrink-0 animate-spin text-sky-600" />
        ) : (
          <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />
        )}
        <Terminal className="size-3.5 shrink-0 text-sky-600 dark:text-sky-400" />
        <span className="truncate font-mono text-xs font-semibold text-sky-800 dark:text-sky-300">
          {call.tool_name}
        </span>
        {result && result.duration_ms > 0 && (
          <span className="ml-auto shrink-0 rounded-full bg-sky-200 px-2 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-800 dark:text-sky-300">
            {result.duration_ms >= 1000
              ? `${(result.duration_ms / 1000).toFixed(1)}s`
              : `${result.duration_ms}ms`}
          </span>
        )}
        {isLoading && (
          <span className="ml-auto shrink-0 text-[10px] font-medium text-sky-500">
            {t("chat.toolRunning")}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        {/* Arguments */}
        <div className="min-w-0">
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
            {t("chat.toolArguments")}
          </span>
          <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-sky-50 p-2 font-mono text-[11px] text-sky-900 dark:bg-sky-950/50 dark:text-sky-200">
            {JSON.stringify(call.arguments, null, 2)}
          </pre>
        </div>

        {/* Result */}
        {result && (
          <details className="group">
            <summary className="flex cursor-pointer items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300">
              <span className="transition-transform group-open:rotate-90">
                &#9654;
              </span>
              {t("chat.toolResult")}
            </summary>
            <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-emerald-50 p-2 font-mono text-[11px] text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">
              {result.result}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}
