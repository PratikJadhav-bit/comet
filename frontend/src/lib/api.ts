import axios from 'axios'
import type { Task, Tool, ApprovalRequest, HealthStatus, TaskCreate, TaskPlan, ApprovalResponse, Config, ToolExecute } from '../types'

const API_BASE = '/api'

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export const api = {
  // Health
  getHealth: () => apiClient.get<HealthStatus>('/health'),

  // Config
  getConfig: () => apiClient.get<Config>('/config'),

  // Tasks
  getTasks: (status?: string, limit = 50, offset = 0) => 
    apiClient.get<Task[]>('/tasks', { params: { status, limit, offset } }),

  getTask: (taskId: number) => apiClient.get<Task>(`/tasks/${taskId}`),

  createTask: (task: TaskCreate) => apiClient.post<Task>('/tasks', task),

  planTask: (taskId: number, instruction: string) => 
    apiClient.post<Task>(`/tasks/${taskId}/plan`, { task_id: taskId, instruction }),

  executeTask: (taskId: number) => 
    apiClient.post<{ status: string; task_id: number }>(`/tasks/${taskId}/execute`),

  pauseTask: (taskId: number) => apiClient.post<{ status: string; task_id: number }>(`/tasks/${taskId}/pause`),

  resumeTask: (taskId: number) => apiClient.post<{ status: string; task_id: number }>(`/tasks/${taskId}/resume`),

  cancelTask: (taskId: number) => apiClient.post<{ status: string; task_id: number }>(`/tasks/${taskId}/cancel`),

  getTaskStatus: (taskId: number) => apiClient.get<{ task_id: number; status: string; progress: number; total_steps: number }>(`/tasks/${taskId}/status`),

  // Approvals
  getApprovals: () => apiClient.get<ApprovalRequest[]>('/approvals/pending'),

  respondApproval: (approval: ApprovalResponse) => 
    apiClient.post<{ status: string; approval_id: string }>('/approvals/respond', approval),

  // Tools
  getTools: (category?: string) => 
    apiClient.get<Tool[]>('/tools', { params: { category } }),

  getToolSchema: (toolName: string) => apiClient.get(`/tools/${toolName}/schema`),

  executeTool: (toolName: string, args: Record<string, any>) => 
    apiClient.post(`/tools/${toolName}/execute`, args),
}

export default api