export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleString()
}

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSecs = Math.floor(diffMs / 1000)
  const diffMins = Math.floor(diffSecs / 60)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSecs < 60) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    CREATED: 'text-muted',
    PLANNING: 'text-accent-primary',
    READY: 'text-accent-success',
    RUNNING: 'text-accent-primary',
    WAITING_FOR_APPROVAL: 'text-accent-warning',
    VERIFYING: 'text-accent-purple',
    COMPLETED: 'text-accent-success',
    FAILED: 'text-accent-danger',
    CANCELLED: 'text-muted',
    PAUSED: 'text-accent-warning',
  }
  return colors[status] || 'text-muted'
}

export function getRiskColor(risk: string): string {
  const colors: Record<string, string> = {
    LOW: 'text-accent-success',
    MODERATE: 'text-accent-warning',
    HIGH: 'text-accent-danger',
  }
  return colors[risk] || 'text-muted'
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str
  return str.slice(0, length) + '...'
}