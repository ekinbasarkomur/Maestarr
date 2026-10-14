import {
  AlertTriangle,
  Check,
  ChevronRight,
  Download,
  ListPlus,
  Loader2,
  ShieldQuestion,
  X,
} from 'lucide-react'
import { useState } from 'react'

import { Badge, Button } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'

import { toolLabel } from './toolMeta'

export interface ToolPartView {
  name: string
  toolCallId: string
  state: string
  input?: unknown
  output?: unknown
  errorText?: string
  approvalId?: string
}

export function ToolActivity({ part }: { part: ToolPartView }) {
  const [open, setOpen] = useState(false)
  const running = part.state === 'input-streaming' || part.state === 'input-available'
  const failed = part.state === 'output-error' || hasError(part.output)
  const denied = part.state === 'output-denied'
  return (
    <div className="text-[13px]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-md py-0.5 text-muted-foreground transition hover:text-foreground"
      >
        {running ? (
          <Loader2 className="size-3.5 animate-spin text-primary" />
        ) : failed ? (
          <AlertTriangle className="size-3.5 text-danger" />
        ) : denied ? (
          <X className="size-3.5" />
        ) : (
          <Check className="size-3.5 text-success" />
        )}
        <span>
          {denied ? `${toolLabel(part.name, false)} — declined` : toolLabel(part.name, !running)}
        </span>
        <ChevronRight className={cn('size-3 transition-transform', open && 'rotate-90')} />
      </button>
      {open && (
        <pre className="scroll-thin mt-1.5 max-h-72 overflow-auto rounded-lg bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground ring-1 ring-white/[0.06]">
          {JSON.stringify({ input: part.input, output: part.output ?? part.errorText }, null, 2)}
        </pre>
      )}
    </div>
  )
}

function hasError(output: unknown): boolean {
  return typeof output === 'object' && output !== null && 'error' in output
}

export function ApprovalCard({
  part,
  summary,
  onRespond,
}: {
  part: ToolPartView
  summary?: string
  onRespond: (approved: boolean) => void
}) {
  const responded = part.state === 'approval-responded'
  return (
    <div className="glass rounded-xl p-4 ring-1 ring-primary/25">
      <div className="flex items-start gap-3">
        <ShieldQuestion className="mt-0.5 size-5 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium tracking-wide text-primary uppercase">
            Needs your approval
          </p>
          <p className="mt-1 text-sm leading-snug">{summary ?? toolLabel(part.name, false)}</p>
        </div>
      </div>
      {!responded ? (
        <div className="mt-3 flex gap-2 pl-8">
          <Button size="sm" variant="primary" onClick={() => onRespond(true)}>
            <Check className="size-3.5" />
            Approve
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onRespond(false)}>
            Deny
          </Button>
        </div>
      ) : (
        <p className="mt-2 pl-8 text-xs text-muted-foreground">Answer sent…</p>
      )}
    </div>
  )
}

export interface ReleaseRow {
  guid: string
  title: string
  size_gb: number
  score: number
  indexer_seeders: number | null
  live_seeders: number | null
  swarm_source: string | null
  coverage: string | null
  bitrate_mbps: number | null
  reasons?: string[]
  blockers: string[]
  quality?: string | null
  indexer?: string | null
}

export interface ReleaseList {
  subject: string
  decided_by?: string
  verdict?: {
    chosen_guid: string | null
    runner_up_guid?: string | null
    rationale: string
    files_to_select?: number | null
  }
  assessed: ReleaseRow[]
  results_id?: string
  more_available?: number
  next_offset?: number
  offset?: number
  depth?: 'quick' | 'full'
}

const SHOWN = 5

/** Judged releases as a pick list: Download on each row, more results on demand. */
export function ReleasePicker({
  data,
  onAsk,
}: {
  data: ReleaseList
  onAsk: (prompt: string) => void
}) {
  const [all, setAll] = useState(false)
  const [asked, setAsked] = useState<Set<string>>(new Set())
  const verdict = data.verdict
  const chosen = verdict?.chosen_guid ?? null
  const rows = all ? data.assessed : data.assessed.slice(0, SHOWN)
  const more = data.more_available ?? 0
  const nextOffset = data.next_offset ?? 0
  const ask = (key: string, prompt: string) => {
    setAsked((s) => new Set(s).add(key))
    onAsk(prompt)
  }
  return (
    <div className="glass overflow-hidden rounded-xl">
      <div className="border-b border-white/[0.06] px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium">
            {verdict ? data.subject : `More results · ${data.subject}`}
          </p>
          {verdict && (
            <Badge tone={chosen ? 'success' : 'danger'}>
              {chosen ? 'pick found' : 'nothing acceptable'}
            </Badge>
          )}
          {verdict && <Badge>{data.decided_by === 'llm' ? 'AI verdict' : 'rules verdict'}</Badge>}
          {data.depth && (
            <Badge>{data.depth === 'quick' ? 'quick check' : 'files and seeders checked'}</Badge>
          )}
        </div>
        {verdict?.rationale && (
          <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
            {verdict.rationale}
          </p>
        )}
      </div>
      <ul>
        {rows.map((r, i) => {
          const isPick = r.guid === chosen
          const isRunnerUp = r.guid === verdict?.runner_up_guid
          const blocked = r.blockers.length > 0
          const seeders = r.live_seeders ?? r.indexer_seeders ?? null
          const meta = [
            `${r.size_gb} GB`,
            seeders !== null ? `${seeders} ${r.live_seeders !== null ? 'live ' : ''}seeders` : null,
            r.bitrate_mbps ? `~${r.bitrate_mbps} Mbps` : null,
            r.coverage ? `covers ${r.coverage}` : null,
            r.quality,
            r.indexer,
          ].filter(Boolean)
          const note = blocked ? r.blockers[0] : r.reasons?.find((x) => !/^\d+p \(/.test(x))
          const done = asked.has(r.guid)
          return (
            <li
              key={r.guid}
              className={cn(
                'flex items-center gap-3 border-t border-white/[0.04] px-4 py-3 first:border-t-0',
                isPick && 'bg-primary/[0.07]',
              )}
            >
              <span
                className={cn(
                  'flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ring-1',
                  isPick ? 'bg-primary text-primary-foreground ring-primary' : 'ring-white/15',
                )}
              >
                {(data.offset ?? 0) + i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-[13px] font-medium" title={r.title}>
                    {r.title}
                  </p>
                  {isPick && <Badge tone="success">Recommended</Badge>}
                  {isRunnerUp && <Badge>Runner-up</Badge>}
                </div>
                <p className="truncate text-[11px] text-muted-foreground">{meta.join(' · ')}</p>
                {note && (
                  <p
                    className={cn(
                      'truncate text-[11px]',
                      blocked ? 'text-danger' : 'text-muted-foreground/80',
                    )}
                    title={note}
                  >
                    {note}
                  </p>
                )}
              </div>
              <span className="hidden w-9 text-right text-xs text-muted-foreground tabular-nums sm:block">
                {Math.round(r.score)}
              </span>
              <Button
                size="sm"
                variant={done ? 'ghost' : isPick ? 'primary' : blocked ? 'ghost' : 'secondary'}
                disabled={done}
                onClick={() =>
                  ask(r.guid, `Download "${r.title}" (guid ${r.guid}) for ${data.subject}.`)
                }
              >
                {done ? <Check className="size-3.5" /> : <Download className="size-3.5" />}
                {done ? 'Requested' : blocked ? 'Anyway' : 'Download'}
              </Button>
            </li>
          )
        })}
      </ul>
      <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.06] px-4 py-2.5">
        {!all && data.assessed.length > SHOWN && (
          <Button size="sm" variant="ghost" onClick={() => setAll(true)}>
            Show all {data.assessed.length}
          </Button>
        )}
        {data.results_id && more > 0 && (
          <Button
            size="sm"
            variant="secondary"
            disabled={asked.has('more')}
            onClick={() =>
              ask(
                'more',
                `Show more results for ${data.subject} (results ${data.results_id}, offset ${nextOffset}).`,
              )
            }
          >
            <ListPlus className="size-3.5" />
            Show more results ({more})
          </Button>
        )}
        {data.depth === 'quick' && data.results_id && (
          <Button
            size="sm"
            variant="ghost"
            disabled={asked.has('deep')}
            onClick={() =>
              ask(
                'deep',
                `Check these releases in depth (results ${data.results_id}, offset ${data.offset ?? 0}).`,
              )
            }
          >
            Check files and seeders
          </Button>
        )}
        <p className="ml-auto text-[11px] text-muted-foreground">
          {verdict?.files_to_select
            ? `Only ${verdict.files_to_select} files of the pack would be downloaded. `
            : ''}
          Downloads ask for approval.
        </p>
      </div>
    </div>
  )
}
