import { isSecret, type SettingValue } from '@/lib/api'
import type { ServiceDef } from '@/lib/services'

export function isConfigured(
  def: ServiceDef,
  saved: Record<string, SettingValue> | undefined,
): boolean {
  if (!saved) return false
  const first = def.fields.find((f) => f.kind !== 'toggle' && !f.optional)
  if (!first) return false
  const v = saved[first.name]
  return isSecret(v) ? v.set : Boolean(v)
}
