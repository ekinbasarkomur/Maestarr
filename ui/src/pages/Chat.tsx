import { useChat } from '@ai-sdk/react'
import {
  DefaultChatTransport,
  getToolName,
  isToolUIPart,
  lastAssistantMessageIsCompleteWithApprovalResponses,
  type UIMessage,
} from 'ai'
import { ArrowUp, MessageSquarePlus, PanelLeft, Pencil, Send, Square, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'

import { Markdown } from '@/components/chat/Markdown'
import { DetailsModal, type DetailsTarget } from '@/components/DetailsModal'
import { PickCarousel } from '@/components/chat/PickCarousel'
import {
  ApprovalCard,
  ToolActivity,
  ReleasePicker,
  type ReleaseList,
  type ToolPartView,
} from '@/components/chat/ToolPart'
import { Badge, Button, Logo, Spinner } from '@/components/ui/primitives'
import { api, type Conversation } from '@/lib/api'
import { detailsToCard, type PickCard, searchPrompt } from '@/lib/picks'
import { cn } from '@/lib/utils'

function newId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
}

export default function ChatPage() {
  const { id: routeId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const initialPrompt = (location.state as { prompt?: string } | null)?.prompt
  // A fresh /chat gets an id up front; the URL follows once the chat exists.
  const [draftId] = useState(newId)
  const id = routeId ?? draftId
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loaded, setLoaded] = useState<{ id: string; messages: UIMessage[] } | null>(null)
  const [sidebar, setSidebar] = useState(false)

  const refreshList = useCallback(() => {
    api
      .conversations()
      .then(setConversations)
      .catch(() => undefined)
  }, [])

  useEffect(() => refreshList(), [refreshList])

  // Saved conversations are fetched; a new one starts empty without a request.
  // When a new chat's first message moves the URL to /chat/<its id>, nothing
  // is refetched, so the live chat keeps its state.
  const isDraft = !routeId || routeId === draftId
  useEffect(() => {
    if (!routeId || routeId === draftId) return
    let alive = true
    api
      .conversation(routeId)
      .then((c) => alive && setLoaded({ id: routeId, messages: c.messages as UIMessage[] }))
      .catch(() => alive && setLoaded({ id: routeId, messages: [] }))
    return () => {
      alive = false
    }
  }, [routeId, draftId])
  const current = isDraft
    ? { id, messages: [] as UIMessage[] }
    : loaded?.id === routeId
      ? loaded
      : null

  return (
    <div className="flex h-full">
      <ConversationSidebar
        conversations={conversations}
        activeId={id}
        open={sidebar}
        onClose={() => setSidebar(false)}
        onNew={() => navigate('/chat')}
        onOpen={(cid) => {
          setSidebar(false)
          navigate(`/chat/${cid}`)
        }}
        onChanged={refreshList}
      />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <button
          className="absolute top-3 left-3 z-10 rounded-lg p-2 text-muted-foreground hover:bg-white/[0.06] lg:hidden"
          onClick={() => setSidebar(true)}
          aria-label="Conversations"
        >
          <PanelLeft className="size-5" />
        </button>
        {current ? (
          <ChatView
            key={id}
            id={id}
            initialMessages={current.messages}
            initialPrompt={isDraft ? initialPrompt : undefined}
            onFirstMessage={() => {
              if (!routeId) navigate(`/chat/${id}`, { replace: true, state: null })
            }}
            onActivity={refreshList}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <Spinner />
          </div>
        )}
      </div>
    </div>
  )
}

function ConversationSidebar({
  conversations,
  activeId,
  open,
  onClose,
  onNew,
  onOpen,
  onChanged,
}: {
  conversations: Conversation[]
  activeId: string
  open: boolean
  onClose: () => void
  onNew: () => void
  onOpen: (id: string) => void
  onChanged: () => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={onClose} />}
      <aside
        className={cn(
          'glass-strong z-40 flex w-72 shrink-0 flex-col border-r border-white/[0.06]',
          'fixed inset-y-0 left-0 transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="p-3">
          <Button variant="secondary" className="w-full justify-start" onClick={onNew}>
            <MessageSquarePlus className="size-4" />
            New conversation
          </Button>
        </div>
        <div className="scroll-thin flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 && (
            <p className="px-3 py-4 text-xs text-muted-foreground">No conversations yet.</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={cn(
                'group flex items-center gap-1 rounded-lg pr-1 transition',
                c.id === activeId ? 'bg-white/[0.08]' : 'hover:bg-white/[0.04]',
              )}
            >
              {editing === c.id ? (
                <form
                  className="flex-1 px-1 py-1"
                  onSubmit={async (e) => {
                    e.preventDefault()
                    await api.renameConversation(c.id, title.trim() || c.title)
                    setEditing(null)
                    onChanged()
                  }}
                >
                  <input
                    autoFocus
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    onBlur={() => setEditing(null)}
                    className="h-8 w-full rounded-md bg-black/30 px-2 text-sm ring-1 ring-white/10 outline-none"
                  />
                </form>
              ) : (
                <button onClick={() => onOpen(c.id)} className="min-w-0 flex-1 px-3 py-2 text-left">
                  <p className="truncate text-sm">{c.title}</p>
                  <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    {new Date(c.updated_at * 1000).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                    })}
                    {c.channel === 'telegram' && <Badge className="py-0">Telegram</Badge>}
                  </p>
                </button>
              )}
              {editing !== c.id && (
                <div className="flex opacity-0 transition group-hover:opacity-100">
                  <button
                    title="Rename"
                    className="rounded p-1.5 text-muted-foreground hover:text-foreground"
                    onClick={() => {
                      setEditing(c.id)
                      setTitle(c.title)
                    }}
                  >
                    <Pencil className="size-3.5" />
                  </button>
                  <button
                    title="Delete"
                    className="rounded p-1.5 text-muted-foreground hover:text-danger"
                    onClick={async () => {
                      if (!window.confirm(`Delete “${c.title}”?`)) return
                      await api.deleteConversation(c.id)
                      onChanged()
                      if (c.id === activeId) onOpen('')
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </aside>
    </>
  )
}

const STARTERS = [
  'Recommend me a melancholic film I have not seen',
  'What is downloading, and is anything stuck?',
  'Judge the releases for the next season of a show I follow',
  'Which series take the most disk space?',
]

function ChatView({
  id,
  initialMessages,
  initialPrompt,
  onFirstMessage,
  onActivity,
}: {
  id: string
  initialMessages: UIMessage[]
  initialPrompt?: string
  onFirstMessage: () => void
  onActivity: () => void
}) {
  const navigate = useNavigate()
  const transport = useMemo(
    () => new DefaultChatTransport({ api: '/api/chat', credentials: 'same-origin' }),
    [],
  )
  const { messages, sendMessage, status, error, stop, addToolApprovalResponse, clearError } =
    useChat({
      id,
      messages: initialMessages,
      transport,
      sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
      onFinish: () => onActivity(),
    })
  const [input, setInput] = useState('')
  const sentInitial = useRef(false)
  const scroller = useRef<HTMLDivElement>(null)
  const busy = status === 'submitted' || status === 'streaming'

  const send = useCallback(
    (text: string) => {
      const value = text.trim()
      if (!value || busy) return
      clearError()
      void sendMessage({ text: value })
      setInput('')
      onFirstMessage()
    },
    [busy, clearError, onFirstMessage, sendMessage],
  )

  useEffect(() => {
    if (initialPrompt && !sentInitial.current) {
      sentInitial.current = true
      send(initialPrompt)
    }
  }, [initialPrompt, send])

  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 240
    if (nearBottom || status === 'submitted')
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, status])

  // Approval summaries arrive as data-approval parts, keyed by tool call.
  const summaries = useMemo(() => {
    const map: Record<string, string> = {}
    for (const m of messages)
      for (const p of m.parts)
        if (p.type === 'data-approval') {
          const d = (p as { data?: { toolCallId?: string; summary?: string } }).data
          if (d?.toolCallId && d.summary) map[d.toolCallId] = d.summary
        }
    return map
  }, [messages])

  const errorText = error ? describeError(error) : null

  const [details, setDetails] = useState<DetailsTarget | null>(null)
  return (
    <>
      {details && (
        <DetailsModal
          target={details}
          onClose={() => setDetails(null)}
          onGet={(d) => {
            setDetails(null)
            send(searchPrompt(detailsToCard(d)))
          }}
          onAsk={(d) => {
            setDetails(null)
            send(
              `Tell me more about ${d.title}${d.year ? ` (${d.year})` : ''} — is it right for me?`,
            )
          }}
        />
      )}
      <div ref={scroller} className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 pt-14 pb-6 sm:px-6 lg:pt-8">
          {messages.length === 0 ? (
            <EmptyState onPick={send} />
          ) : (
            <div className="space-y-6">
              {messages.map((m) => (
                <MessageRow
                  key={m.id}
                  message={m}
                  summaries={summaries}
                  onApproval={(approvalId, approved) =>
                    addToolApprovalResponse({ id: approvalId, approved })
                  }
                  onAsk={send}
                  onOpen={(c) =>
                    setDetails({
                      kind: c.kind,
                      tmdb_id: c.tmdb_id,
                      tvdb_id: c.tvdb_id,
                      stash_id: c.stash_id,
                      title: c.title,
                      year: c.year,
                      poster: c.image,
                      why: c.why,
                    })
                  }
                />
              ))}
              {status === 'submitted' && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                    <span className="relative inline-flex size-2 rounded-full bg-primary" />
                  </span>
                  Thinking…
                </div>
              )}
            </div>
          )}
          {errorText && (
            <div className="mt-6 rounded-xl bg-danger/10 px-4 py-3 text-sm text-danger ring-1 ring-danger/25">
              {errorText.text}
              {errorText.settings && (
                <button className="ml-2 underline" onClick={() => navigate('/settings/ai')}>
                  Open AI settings
                </button>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="px-4 pb-4 sm:px-6">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            send(input)
          }}
          className="glass mx-auto flex max-w-3xl items-end gap-2 rounded-2xl p-2 pl-4"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                send(input)
              }
            }}
            rows={1}
            placeholder="Message Maestarr…"
            className="scroll-thin max-h-48 min-h-[44px] flex-1 resize-none bg-transparent py-3 text-[15px] outline-none placeholder:text-muted-foreground/70 [field-sizing:content]"
          />
          {busy ? (
            <Button
              type="button"
              size="md"
              variant="secondary"
              onClick={() => void stop()}
              title="Stop"
            >
              <Square className="size-4 fill-current" />
            </Button>
          ) : (
            <Button type="submit" size="md" variant="primary" disabled={!input.trim()} title="Send">
              <ArrowUp className="size-4" />
            </Button>
          )}
        </form>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground/70">
          Maestarr asks before it downloads, adds or deletes anything.
        </p>
      </div>
    </>
  )
}

function describeError(error: Error): { text: string; settings: boolean } {
  const raw = error.message || ''
  if (raw.includes('ai_not_configured'))
    return { text: 'No AI provider is set up yet.', settings: true }
  try {
    const body = JSON.parse(raw)
    if (body?.message) return { text: body.message, settings: false }
    if (typeof body?.detail === 'string') return { text: body.detail, settings: false }
    // A validation error (a list of pydantic errors) is never useful to read.
    if (Array.isArray(body) || Array.isArray(body?.detail))
      return { text: 'The server could not read this chat. Try sending again.', settings: false }
  } catch {
    // plain text
  }
  if (raw.length > 300) return { text: 'Something went wrong. Try sending again.', settings: false }
  return { text: raw || 'Something went wrong.', settings: false }
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center pt-[12vh] text-center">
      <Logo className="size-14" />
      <h1 className="mt-5 text-2xl font-semibold tracking-tight">
        How can I help with your library?
      </h1>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        Recommendations from your history, the best release for anything you want, and everything in
        Sonarr, Radarr and qBittorrent.
      </p>
      <div className="mt-8 grid w-full max-w-xl gap-2 sm:grid-cols-2">
        {STARTERS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="glass flex items-start gap-2 rounded-xl px-4 py-3 text-left text-sm text-muted-foreground transition hover:text-foreground"
          >
            <Send className="mt-0.5 size-3.5 shrink-0 text-primary" />
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

function MessageRow({
  message,
  summaries,
  onApproval,
  onAsk,
  onOpen,
}: {
  message: UIMessage
  summaries: Record<string, string>
  onApproval: (approvalId: string, approved: boolean) => void
  onAsk: (text: string) => void
  onOpen: (card: PickCard) => void
}) {
  if (message.role === 'user') {
    const text = message.parts.map((p) => (p.type === 'text' ? p.text : '')).join('')
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-white/[0.09] px-4 py-2.5 text-[15px] whitespace-pre-wrap ring-1 ring-white/[0.06]">
          {text}
        </div>
      </div>
    )
  }
  return (
    <div className="flex gap-3">
      <Logo className="mt-0.5 size-7 shrink-0" />
      <div className="min-w-0 flex-1 space-y-2.5">
        {message.parts.map((part, i) => {
          if (part.type === 'text') return part.text ? <Markdown key={i} text={part.text} /> : null
          if (!isToolUIPart(part)) return null
          const p = part as unknown as {
            toolCallId: string
            state: string
            input?: unknown
            output?: unknown
            errorText?: string
            approval?: { id: string }
          }
          const view: ToolPartView = {
            name: getToolName(part),
            toolCallId: p.toolCallId,
            state: p.state,
            input: p.input,
            output: p.output,
            errorText: p.errorText,
            approvalId: p.approval?.id,
          }
          if (
            (p.state === 'approval-requested' || p.state === 'approval-responded') &&
            p.approval
          ) {
            return (
              <ApprovalCard
                key={i}
                part={view}
                summary={summaries[p.toolCallId]}
                onRespond={(approved) => onApproval(p.approval!.id, approved)}
              />
            )
          }
          const output = p.output as Record<string, unknown> | undefined
          if (
            (view.name === 'judge_releases' || view.name === 'more_releases') &&
            p.state === 'output-available' &&
            Array.isArray(output?.assessed)
          ) {
            return (
              <div key={i} className="space-y-1.5">
                <ToolActivity part={view} />
                <ReleasePicker data={output as unknown as ReleaseList} onAsk={onAsk} />
              </div>
            )
          }
          if (
            view.name === 'show_recommendations' &&
            p.state === 'output-available' &&
            Array.isArray(output?.cards)
          ) {
            return (
              <div key={i} className="space-y-2">
                <ToolActivity part={view} />
                <PickCarousel
                  cards={output.cards as PickCard[]}
                  onSearch={(c) => onAsk(searchPrompt(c))}
                  onOpen={onOpen}
                />
              </div>
            )
          }
          return <ToolActivity key={i} part={view} />
        })}
      </div>
    </div>
  )
}
