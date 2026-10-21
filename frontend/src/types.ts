export interface HealthStatus {
  status: string
  model_connected: boolean
  version: string
}

export interface Tool {
  name: string
  description: string
  category: string
  parameters: ToolParameter[]
  risk_level: string
  requires_approval: boolean
}

export interface ToolParameter {
  name: string
  type: string
  description: string
  required: boolean
}

export interface Task {
  id: number
  task_id: string
  title: string
  description: string
  status: TaskStatus
  plan?: any
  result?: any
  tool_calls: ToolCall[]
  created_at: string
  started_at?: string
  completed_at?: string
  error_message?: string
}

export type TaskStatus = 
  | 'CREATED'
  | 'PLANNING'
  | 'READY'
  | 'RUNNING'
  | 'WAITING_FOR_APPROVAL'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'PAUSED'

export interface ToolCall {
  id: number
  call_id: string
  tool_name: string
  status: ToolCallStatus
  arguments: Record<string, any>
  result?: any
  error_message?: string
  retry_count: number
  created_at: string
  started_at?: string
  completed_at?: string
}

export type ToolCallStatus = 
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export interface ApprovalRequest {
  approval_id: string
  task_id: number
  tool_call_id?: number
  risk_level: 'LOW' | 'MODERATE' | 'HIGH'
  title: string
  description: string
  details: Record<string, any>
  status: ApprovalStatus
  requested_at: string
  expires_at?: string
}

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'CANCELLED'

export interface TaskCreate {
  title: string
  description?: string
  parent_task_id?: number
  metadata?: Record<string, any>
}

export interface TaskPlan {
  task_id: number
  instruction: string
}

export interface TaskExecute {
  task_id: number
}

export interface ApprovalResponse {
  approval_id: string
  approved: boolean
  reason?: string
}

export interface ToolExecute {
  tool_name: string
  arguments: Record<string, any>
}

export interface Config {
  app_name: string
  app_version: string
  model_provider: string
  model_name: string
  browser_headless: boolean
  allowed_directories: string[]
  max_file_size_mb: number
  max_task_duration_seconds: number
  max_tool_calls_per_task: number
}