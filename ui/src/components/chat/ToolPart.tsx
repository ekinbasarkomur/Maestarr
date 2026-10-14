import { AlertTriangle, Check, ChevronRight, Loader2, ShieldQuestion, X } from 'lucide-react'
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

interface Verdict {
  subject: string
  decided_by: string
  verdict: {
    chosen_guid: string | null
    rationale: string
    confidence: string
    warnings: string[]
    files_to_select?: number | null
  }
  assessed: {
    guid: string
    title: string
    size_gb: number
    score: number
    indexer_seeders: number | null
    live_seeders: number | null
    swarm_source: string | null
    coverage: string | null
    bitrate_mbps: number | null
    blockers: string[]
  }[]
}

export function VerdictCard({ data }: { data: Verdict }) {
  const chosen = data.assessed.find((a) => a.guid === data.verdict.chosen_guid)
  return (
    <div className="glass overflow-hidden rounded-xl">
      <div className="border-b border-white/[0.06] px-4 py-3">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{data.subject}</p>
          <Badge tone={chosen ? 'success' : 'danger'}>
            {chosen ? 'pick found' : 'nothing acceptable'}
          </Badge>
          <Badge>{data.decided_by === 'llm' ? 'AI verdict' : 'rules verdict'}</Badge>
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
          {data.verdict.rationale}
        </p>
      </div>
      <table className="w-full text-[12px]">
        <thead className="text-muted-foreground">
          <tr className="text-left">
            <th className="px-4 py-2 font-medium">Release</th>
            <th className="px-2 py-2 text-right font-medium">Size</th>
            <th className="px-2 py-2 text-right font-medium">Seeders</th>
            <th className="hidden px-2 py-2 text-right font-medium sm:table-cell">Coverage</th>
            <th className="px-4 py-2 text-right font-medium">Score</th>
          </tr>
        </thead>
        <tbody>
          {data.assessed.slice(0, 6).map((a) => (
            <tr
              key={a.guid}
              className={cn(
                'border-t border-white/[0.04]',
                a.guid === data.verdict.chosen_guid && 'bg-primary/[0.07]',
              )}
            >
              <td className="max-w-0 px-4 py-2">
                <p className="truncate" title={a.title}>
                  {a.title}
                </p>
                {a.blockers.length > 0 && (
                  <p className="truncate text-[11px] text-danger">{a.blockers[0]}</p>
                )}
              </td>
              <td className="px-2 py-2 text-right tabular-nums">{a.size_gb} GB</td>
              <td className="px-2 py-2 text-right tabular-nums">
                {a.live_seeders ?? '–'}
                {a.swarm_source === 'scrape' &&
                  a.indexer_seeders !== null &&
                  a.indexer_seeders !== a.live_seeders && (
                    <span className="text-muted-foreground"> / {a.indexer_seeders}</span>
                  )}
              </td>
              <td className="hidden px-2 py-2 text-right tabular-nums sm:table-cell">
                {a.coverage ?? '–'}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{Math.round(a.score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-white/[0.04] px-4 py-2 text-[11px] text-muted-foreground">
        Seeders are live tracker numbers
        {data.assessed.some((a) => a.swarm_source === 'scrape')
          ? ' (indexer claim after the slash)'
          : ''}
        .
        {data.verdict.files_to_select
          ? ` Only ${data.verdict.files_to_select} files of the pack would be downloaded.`
          : ''}
      </p>
    </div>
  )
}
