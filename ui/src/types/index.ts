export interface Health {
  status: string
  version: string
}

export interface ServiceStatus {
  name: string
  configured: boolean
  ok: boolean
  version?: string | null
  detail?: string | null
}

export interface StatusResponse {
  version: string
  model: string
  services: ServiceStatus[]
}

export interface ConversationSummary {
  id: string
  channel: string
  title: string
  created_at: number
  updated_at: number
}

export interface QueueItem {
  app: string
  queue_id: number
  title: string
  status: string
  state?: string
  progress_pct?: number | null
  size_gb: number
  eta?: string | null
  problems: string[]
}

export interface Disk {
  path: string
  free_gb: number
  total_gb: number
}

export interface QueueResponse {
  queue: QueueItem[]
  disks: Disk[]
  download_mbps?: number
  error?: string
}
