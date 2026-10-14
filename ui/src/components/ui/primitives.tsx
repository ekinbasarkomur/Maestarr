import { Check, Eye, EyeOff, Loader2 } from 'lucide-react'
import {
  forwardRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react'

import { cn } from '@/lib/utils'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const variants: Record<Variant, string> = {
  primary:
    'bg-primary text-primary-foreground hover:brightness-110 shadow-[0_6px_20px_-8px_rgba(212,166,74,.6)]',
  secondary: 'bg-white/[0.07] text-foreground hover:bg-white/[0.11] ring-1 ring-white/10',
  ghost: 'text-muted-foreground hover:text-foreground hover:bg-white/[0.06]',
  danger: 'bg-danger/15 text-danger ring-1 ring-danger/30 hover:bg-danger/25',
}
const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-[13px] gap-1.5 rounded-md',
  md: 'h-10 px-4 text-sm gap-2 rounded-lg',
  lg: 'h-12 px-6 text-[15px] gap-2 rounded-xl',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, className, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex shrink-0 items-center justify-center font-medium transition-all duration-150 outline-none select-none',
        'focus-visible:ring-2 focus-visible:ring-ring/60 disabled:cursor-not-allowed disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  )
})

const fieldBase =
  'w-full rounded-lg bg-black/25 px-3.5 text-sm text-foreground ring-1 ring-white/10 placeholder:text-muted-foreground/60 outline-none transition focus:ring-2 focus:ring-ring/50 disabled:opacity-60'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(fieldBase, 'h-10', className)} {...props} />
  },
)

export function SecretInput({
  saved,
  value,
  onChange,
  placeholder,
  id,
}: {
  saved: boolean
  value: string
  onChange: (v: string) => void
  placeholder?: string
  id?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? 'text' : 'password'}
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={saved && !value ? '•••••••••••• saved — type to replace' : placeholder}
        className="pr-10 font-mono"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
        aria-label={show ? 'Hide' : 'Show'}
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  )
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        fieldBase,
        'h-10 appearance-none bg-[length:16px] pr-9',
        'select-chevron',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
}

export function Field({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: string
  hint?: ReactNode
  htmlFor?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="block text-[13px] font-medium text-foreground/90">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  description?: ReactNode
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition',
          checked ? 'bg-primary' : 'bg-white/15',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow transition-transform',
            checked && 'translate-x-4',
          )}
        />
      </button>
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="block text-xs text-muted-foreground">{description}</span>}
      </span>
    </label>
  )
}

export function Badge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'accent'
  children: ReactNode
  className?: string
}) {
  const tones = {
    neutral: 'bg-white/[0.07] text-muted-foreground ring-white/10',
    success: 'bg-success/12 text-success ring-success/25',
    warning: 'bg-primary/12 text-primary ring-primary/25',
    danger: 'bg-danger/12 text-danger ring-danger/25',
    accent: 'bg-primary/15 text-primary ring-primary/30',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function StatusDot({ state }: { state: 'ok' | 'down' | 'off' }) {
  return (
    <span
      className={cn(
        'inline-block size-2 rounded-full',
        state === 'ok' && 'bg-success shadow-[0_0_8px_rgba(95,179,138,.7)]',
        state === 'down' && 'bg-danger shadow-[0_0_8px_rgba(224,108,108,.6)]',
        state === 'off' && 'bg-white/20',
      )}
    />
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('size-4 animate-spin text-muted-foreground', className)} />
}

export function Panel({ className, children }: { className?: string; children?: ReactNode }) {
  return <div className={cn('glass rounded-2xl', className)}>{children}</div>
}

export function SuccessLine({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-center gap-1.5 text-xs text-success">
      <Check className="size-3.5" />
      {children}
    </p>
  )
}

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <rect width="64" height="64" rx="16" fill="#12141b" />
      <path d="M18 46 46 18" stroke="#d4a64a" strokeWidth="5" strokeLinecap="round" />
      <circle cx="18" cy="46" r="6" fill="#d4a64a" />
      <path
        d="M38 44c4-1 7-4 8-8"
        stroke="#e8e6e1"
        strokeOpacity=".55"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}
