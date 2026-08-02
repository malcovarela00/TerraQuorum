import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Bot,
  Mic,
  MicOff,
  Plus,
  SendHorizontal,
  Sparkles,
  Square,
  User as UserIcon,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useChatStream from "@/hooks/useChatStream"
import useCustomToast from "@/hooks/useCustomToast"
import { useI18n } from "@/i18n"
import { cn } from "@/lib/utils"

import StreamingMessage from "./StreamingMessage"
import ThinkingBlock from "./ThinkingBlock"
import ToolCallBlock from "./ToolCallBlock"

type ChatProvider = "openai" | "anthropic" | "deepseek" | "google"

type ChatConversation = {
  id: string
  title: string
  created_at: string
  updated_at: string
  owner_id: string
}

type ChatMessageMetadata = {
  thinking?: string
  tool_calls?: {
    tool_name: string
    arguments: Record<string, unknown>
    result_summary?: string
  }[]
}

type ChatMessage = {
  id: string
  role: string
  content: string
  provider?: string | null
  model?: string | null
  metadata?: ChatMessageMetadata | null
  conversation_id: string
  created_at: string
}

type ChatConversationsResponse = {
  data: ChatConversation[]
  count: number
}

type ChatMessagesResponse = {
  data: ChatMessage[]
  count: number
}

type ChatAudioTranscriptionResponse = {
  text: string
}

const PROVIDER_MODELS: Record<ChatProvider, string[]> = {
  openai: ["gpt-5.5"],
  anthropic: ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"],
  deepseek: ["deepseek-v4"],
  google: ["gemini-3.1-pro", "gemini-3.1-flash"],
}

const API_BASE = import.meta.env.VITE_API_URL ?? ""
const RECORDING_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
]

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("access_token") ?? ""
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    const detail =
      typeof errorBody?.detail === "string"
        ? errorBody.detail
        : "Error al comunicarse con el chat."
    throw new Error(detail)
  }

  return (await response.json()) as T
}

function listConversations() {
  return fetchApi<ChatConversationsResponse>("/api/v1/chats/")
}

function createConversation(title: string) {
  return fetchApi<ChatConversation>("/api/v1/chats/", {
    method: "POST",
    body: JSON.stringify({ title }),
  })
}

function listMessages(conversationId: string) {
  return fetchApi<ChatMessagesResponse>(
    `/api/v1/chats/${conversationId}/messages`,
  )
}

function getSupportedRecordingMimeType() {
  if (typeof MediaRecorder === "undefined") return undefined
  return RECORDING_MIME_TYPES.find((mimeType) =>
    MediaRecorder.isTypeSupported(mimeType),
  )
}

function getAudioExtension(contentType: string) {
  if (contentType.includes("mp4")) return "m4a"
  if (contentType.includes("ogg")) return "ogg"
  if (contentType.includes("wav")) return "wav"
  return "webm"
}

function stopMediaStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => {
    track.stop()
  })
}

async function transcribeAudio(audioBlob: Blob) {
  const token = localStorage.getItem("access_token") ?? ""
  const formData = new FormData()
  const extension = getAudioExtension(audioBlob.type)
  formData.append("audio", audioBlob, `recording.${extension}`)

  const response = await fetch(
    `${API_BASE}/api/v1/chats/audio/transcriptions`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    },
  )

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    const detail =
      typeof errorBody?.detail === "string"
        ? errorBody.detail
        : "Error al transcribir el audio."
    throw new Error(detail)
  }

  return (await response.json()) as ChatAudioTranscriptionResponse
}

export default function DashboardAiChat() {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const { t } = useI18n()
  const [selectedConversationId, setSelectedConversationId] =
    useState<string>("")
  const [provider, setProvider] = useState<ChatProvider>("openai")
  const [model, setModel] = useState<string>(PROVIDER_MODELS.openai[0])
  const [prompt, setPrompt] = useState("")
  const [pendingMessage, setPendingMessage] = useState<string | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const audioChunksRef = useRef<BlobPart[]>([])
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)

  const {
    streamingState,
    sendStreamingMessage,
    abortStream,
    reset: resetStream,
  } = useChatStream(selectedConversationId)

  const conversationQuery = useQuery({
    queryKey: ["chat-conversations"],
    queryFn: listConversations,
  })

  const conversations = conversationQuery.data?.data ?? []

  const messagesQuery = useQuery({
    queryKey: ["chat-messages", selectedConversationId],
    queryFn: () => listMessages(selectedConversationId),
    enabled: Boolean(selectedConversationId),
  })

  const createConversationMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ["chat-conversations"] })
      setSelectedConversationId(conversation.id)
      showSuccessToast(t("chat.created"))
      if (pendingMessage) {
        sendStreamingMessage({
          message: pendingMessage,
          provider,
          model,
        })
        setPendingMessage(null)
      }
    },
    onError: (error: Error) => showErrorToast(error.message),
  })

  const transcribeAudioMutation = useMutation({
    mutationFn: transcribeAudio,
    onSuccess: ({ text }) => {
      const transcript = text.trim()
      if (!transcript) return
      setPrompt((current) =>
        current.trim() ? `${current.trim()} ${transcript}` : transcript,
      )
      showSuccessToast(t("chat.audioTranscribed"))
    },
    onError: (error: Error) => showErrorToast(error.message),
  })

  useEffect(() => {
    if (conversations.length > 0 && !selectedConversationId) {
      setSelectedConversationId(conversations[0].id)
    }
  }, [conversations, selectedConversationId])

  const modelOptions = useMemo(() => PROVIDER_MODELS[provider], [provider])

  useEffect(() => {
    setModel(modelOptions[0])
  }, [modelOptions])

  const messages = messagesQuery.data?.data ?? []

  // Auto-scroll cuando llegan mensajes nuevos o avanza el streaming
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const hasStreamedContent =
      streamingState.contentText.length > 0 ||
      streamingState.thinkingText.length > 0 ||
      streamingState.toolCalls.length > 0
    if (messages.length > 0 || hasStreamedContent) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
    }
  }, [
    messages.length,
    streamingState.contentText,
    streamingState.thinkingText,
    streamingState.toolCalls.length,
  ])

  // Reset streaming state when conversation changes
  useEffect(() => {
    resetStream()
  }, [resetStream])

  useEffect(() => {
    return () => {
      const recorder = mediaRecorderRef.current
      if (recorder) {
        recorder.onstop = null
      }
      if (recorder?.state === "recording") {
        recorder.stop()
      }
      stopMediaStream(mediaStreamRef.current)
    }
  }, [])

  // Show error toast from stream
  useEffect(() => {
    if (streamingState.error) {
      showErrorToast(streamingState.error)
    }
  }, [streamingState.error, showErrorToast])

  const createDefaultConversationIfNeeded = () => {
    if (conversations.length === 0 && !createConversationMutation.isPending) {
      setPendingMessage(prompt.trim())
      createConversationMutation.mutate(t("chat.defaultConversation"))
      return
    }
    if (!selectedConversationId && conversations.length > 0) {
      setSelectedConversationId(conversations[0].id)
    }
  }

  const handleSend = () => {
    const text = prompt.trim()
    if (!text || streamingState.isStreaming) return
    if (!selectedConversationId) {
      createDefaultConversationIfNeeded()
      return
    }
    setPrompt("")
    sendStreamingMessage({ message: text, provider, model })
  }

  const stopRecording = () => {
    const recorder = mediaRecorderRef.current
    if (recorder?.state === "recording") {
      recorder.stop()
    }
  }

  const handleToggleRecording = async () => {
    if (isRecording) {
      stopRecording()
      return
    }

    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      showErrorToast(t("chat.audioUnsupported"))
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = getSupportedRecordingMimeType()
      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined,
      )

      audioChunksRef.current = []
      mediaStreamRef.current = stream
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      recorder.onstop = () => {
        setIsRecording(false)
        stopMediaStream(stream)
        mediaStreamRef.current = null
        mediaRecorderRef.current = null

        const audioBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        })
        audioChunksRef.current = []

        if (audioBlob.size === 0) {
          showErrorToast(t("chat.audioEmpty"))
          return
        }
        transcribeAudioMutation.mutate(audioBlob)
      }

      recorder.start()
      setIsRecording(true)
    } catch (error) {
      setIsRecording(false)
      stopMediaStream(mediaStreamRef.current)
      mediaStreamRef.current = null
      mediaRecorderRef.current = null
      showErrorToast(
        error instanceof DOMException && error.name === "NotAllowedError"
          ? t("chat.audioPermissionDenied")
          : t("chat.audioStartError"),
      )
    }
  }

  const isBusy =
    streamingState.isStreaming ||
    createConversationMutation.isPending ||
    transcribeAudioMutation.isPending

  const suggestions = [
    t("chat.suggestion1"),
    t("chat.suggestion2"),
    t("chat.suggestion3"),
  ]

  return (
    <Card className="h-[calc(100dvh-10.5rem)] min-h-[620px] border-border/60 bg-gradient-to-b from-card to-muted/10 xl:min-h-[700px]">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 items-center gap-2.5">
            <span className="icon-chip size-9 rounded-lg">
              <Sparkles className="size-4.5" />
            </span>
            <span className="truncate">{t("chat.title")}</span>
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              createConversationMutation.mutate(
                `Conversación ${new Date().toLocaleString()}`,
              )
            }
            disabled={createConversationMutation.isPending}
          >
            <Plus className="size-4" />
            {t("chat.new")}
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex h-full min-h-0 flex-col gap-3">
        <Select
          value={selectedConversationId}
          onValueChange={setSelectedConversationId}
          disabled={conversationQuery.isLoading || conversations.length === 0}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t("chat.selectConversation")} />
          </SelectTrigger>
          <SelectContent>
            {conversations.map((conversation) => (
              <SelectItem key={conversation.id} value={conversation.id}>
                {conversation.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="grid grid-cols-2 gap-2">
          <Select
            value={provider}
            onValueChange={(value) => setProvider(value as ChatProvider)}
          >
            <SelectTrigger>
              <SelectValue placeholder={t("chat.provider")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="openai">OpenAI</SelectItem>
              <SelectItem value="anthropic">Anthropic</SelectItem>
              <SelectItem value="deepseek">DeepSeek</SelectItem>
              <SelectItem value="google">Google</SelectItem>
            </SelectContent>
          </Select>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger>
              <SelectValue placeholder={t("chat.model")} />
            </SelectTrigger>
            <SelectContent>
              {modelOptions.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div
          ref={scrollRef}
          className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto rounded-xl border border-border/60 bg-muted/15 p-3 dark:bg-muted/10"
        >
          {messages.length === 0 && !streamingState.isStreaming ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4 py-8 text-center">
              <span className="flex size-14 items-center justify-center rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/15 to-chart-3/15 text-primary shadow-sm">
                <Sparkles className="size-6" />
              </span>
              <div>
                <p className="font-display text-base font-semibold">
                  {t("chat.emptyTitle")}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t("chat.empty")}
                </p>
              </div>
              <div className="flex w-full max-w-sm flex-col gap-2">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setPrompt(suggestion)}
                    className="rounded-xl border border-border/70 bg-background/80 px-3.5 py-2.5 text-left text-sm text-foreground/90 shadow-xs transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:bg-accent hover:shadow-sm"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => {
              const isUser = message.role === "user"
              return (
                <div
                  key={message.id}
                  className={cn(
                    "flex min-w-0 items-end gap-2",
                    isUser ? "flex-row-reverse" : "flex-row",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "mb-0.5 flex size-7 shrink-0 items-center justify-center rounded-full shadow-sm",
                      isUser
                        ? "bg-primary text-primary-foreground"
                        : "border border-border/70 bg-background text-muted-foreground",
                    )}
                  >
                    {isUser ? (
                      <UserIcon className="size-3.5" />
                    ) : (
                      <Bot className="size-3.5" />
                    )}
                  </span>
                  <div className="flex min-w-0 max-w-[85%] flex-col gap-2">
                    {/* Metadatos de mensajes persistidos del asistente */}
                    {message.role === "assistant" && message.metadata && (
                      <>
                        {message.metadata.tool_calls?.map((tc, i) => (
                          <ToolCallBlock
                            key={i}
                            call={{
                              tool_name: tc.tool_name,
                              arguments: tc.arguments,
                            }}
                            result={
                              tc.result_summary
                                ? {
                                    tool_name: tc.tool_name,
                                    result: tc.result_summary,
                                    duration_ms: 0,
                                  }
                                : undefined
                            }
                          />
                        ))}
                        {message.metadata.thinking && (
                          <ThinkingBlock text={message.metadata.thinking} />
                        )}
                      </>
                    )}
                    <div
                      className={
                        isUser
                          ? "rounded-2xl rounded-br-sm bg-gradient-to-br from-primary to-primary/85 px-3.5 py-2.5 text-sm text-primary-foreground shadow-sm"
                          : "min-w-0 rounded-2xl rounded-bl-sm border border-border/70 bg-background px-3.5 py-2.5 text-sm whitespace-pre-wrap break-words shadow-sm"
                      }
                    >
                      {message.content}
                    </div>
                  </div>
                </div>
              )
            })
          )}

          {/* Streaming message in progress */}
          {streamingState.isStreaming && (
            <StreamingMessage state={streamingState} />
          )}
        </div>

        <div className="flex gap-2">
          <Input
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={t("chat.inputPlaceholder")}
            disabled={transcribeAudioMutation.isPending}
            className="h-10 rounded-xl border-border/70 bg-background/90 px-4 shadow-sm"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                handleSend()
              }
            }}
          />
          <Button
            type="button"
            variant={isRecording ? "destructive" : "outline"}
            size="icon"
            onClick={handleToggleRecording}
            disabled={
              streamingState.isStreaming || transcribeAudioMutation.isPending
            }
            aria-label={
              isRecording ? t("chat.stopRecording") : t("chat.startRecording")
            }
            title={
              isRecording ? t("chat.stopRecording") : t("chat.startRecording")
            }
          >
            <span className="relative inline-flex items-center justify-center gap-1">
              {isRecording ? (
                <MicOff className="size-4" />
              ) : (
                <Mic className="size-4" />
              )}
              {isRecording && (
                <span className="inline-flex items-end gap-0.5">
                  <span
                    className="h-2 w-0.5 animate-bounce rounded-full bg-white/90"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="h-3 w-0.5 animate-bounce rounded-full bg-white/90"
                    style={{ animationDelay: "120ms" }}
                  />
                  <span
                    className="h-2 w-0.5 animate-bounce rounded-full bg-white/90"
                    style={{ animationDelay: "240ms" }}
                  />
                </span>
              )}
              {isRecording && (
                <span className="absolute inset-0 -z-10 rounded-md bg-white/10 blur-[6px]" />
              )}
            </span>
          </Button>
          {streamingState.isStreaming ? (
            <Button variant="destructive" onClick={abortStream}>
              <Square className="size-4" />
              {t("actions.stop")}
            </Button>
          ) : (
            <LoadingButton
              loading={isBusy}
              onClick={handleSend}
              disabled={!prompt.trim() || isBusy}
            >
              <SendHorizontal className="size-4" />
              {t("actions.send")}
            </LoadingButton>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
