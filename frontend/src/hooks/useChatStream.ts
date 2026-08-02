import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useRef, useState } from "react"
import { useI18n } from "@/i18n"

export type ToolCallEvent = {
  tool_name: string
  arguments: Record<string, unknown>
}

export type ToolResultEvent = {
  tool_name: string
  result: string
  duration_ms: number
}

export type StreamingState = {
  isStreaming: boolean
  thinkingText: string
  contentText: string
  toolCalls: ToolCallEvent[]
  toolResults: ToolResultEvent[]
  error: string | null
}

const INITIAL_STATE: StreamingState = {
  isStreaming: false,
  thinkingText: "",
  contentText: "",
  toolCalls: [],
  toolResults: [],
  error: null,
}

const API_BASE = import.meta.env.VITE_API_URL ?? ""

export default function useChatStream(conversationId: string) {
  const queryClient = useQueryClient()
  const { t } = useI18n()
  const [state, setState] = useState<StreamingState>(INITIAL_STATE)
  const abortRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => setState(INITIAL_STATE), [])

  const sendStreamingMessage = useCallback(
    async (payload: { message: string; provider: string; model: string }) => {
      reset()
      setState((s) => ({ ...s, isStreaming: true }))

      const controller = new AbortController()
      abortRef.current = controller

      const token = localStorage.getItem("access_token") ?? ""

      try {
        const response = await fetch(
          `${API_BASE}/api/v1/chats/${conversationId}/messages/stream`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              message: payload.message,
              provider: payload.provider,
              model: payload.model,
              temperature: 0.2,
            }),
            signal: controller.signal,
          },
        )

        if (!response.ok) {
          const body = await response.json().catch(() => ({}))
          const detail =
            typeof body?.detail === "string" ? body.detail : t("chat.error")
          setState((s) => ({ ...s, isStreaming: false, error: detail }))
          return
        }

        const reader = response.body?.getReader()
        if (!reader) {
          setState((s) => ({
            ...s,
            isStreaming: false,
            error: t("chat.error"),
          }))
          return
        }

        const decoder = new TextDecoder()
        let buffer = ""

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Split on double-newline to get complete SSE events
          const parts = buffer.split("\n\n")
          // Last part might be incomplete
          buffer = parts.pop() ?? ""

          for (const part of parts) {
            if (!part.trim()) continue

            let eventType = ""
            let eventData = ""

            for (const line of part.split("\n")) {
              if (line.startsWith("event: ")) {
                eventType = line.slice(7).trim()
              } else if (line.startsWith("data: ")) {
                eventData = line.slice(6)
              }
            }

            if (!eventType || !eventData) continue

            try {
              const data = JSON.parse(eventData)
              switch (eventType) {
                case "tool_call":
                  setState((s) => ({
                    ...s,
                    toolCalls: [
                      ...s.toolCalls,
                      {
                        tool_name: data.tool_name,
                        arguments: data.arguments,
                      },
                    ],
                  }))
                  break
                case "tool_result":
                  setState((s) => ({
                    ...s,
                    toolResults: [
                      ...s.toolResults,
                      {
                        tool_name: data.tool_name,
                        result: data.result,
                        duration_ms: data.duration_ms,
                      },
                    ],
                  }))
                  break
                case "thinking":
                  setState((s) => ({
                    ...s,
                    thinkingText: s.thinkingText + data.content,
                  }))
                  break
                case "content":
                  setState((s) => ({
                    ...s,
                    contentText: s.contentText + data.content,
                  }))
                  break
                case "done":
                  setState((s) => ({ ...s, isStreaming: false }))
                  queryClient.invalidateQueries({
                    queryKey: ["chat-messages", conversationId],
                  })
                  queryClient.invalidateQueries({
                    queryKey: ["chat-conversations"],
                  })
                  queryClient.invalidateQueries({
                    queryKey: ["countries-map-data"],
                  })
                  break
                case "error":
                  setState((s) => ({
                    ...s,
                    isStreaming: false,
                    error: data.detail,
                  }))
                  break
              }
            } catch {
              // skip malformed JSON
            }
          }
        }

        // Stream ended without a done event
        setState((s) => (s.isStreaming ? { ...s, isStreaming: false } : s))
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setState((s) => ({ ...s, isStreaming: false }))
          return
        }
        setState((s) => ({
          ...s,
          isStreaming: false,
          error: err instanceof Error ? err.message : t("errors.generic"),
        }))
      } finally {
        abortRef.current = null
      }
    },
    [conversationId, queryClient, reset, t],
  )

  const abortStream = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { streamingState: state, sendStreamingMessage, abortStream, reset }
}
