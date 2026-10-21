import { useState, useEffect, useRef } from 'react'
import { cn, formatRelativeTime, getStatusColor, getRiskColor, truncate } from '../lib/utils'
import { api } from '../lib/api'
import type { Tool, Task, ApprovalRequest } from '../types'
import { MessageSquare, Send, Bot, User, Loader2, AlertTriangle, CheckCircle, XCircle, ChevronDown, ChevronUp, Copy, Clipboard } from './icons'

interface ChatPanelProps {
  tools: Tool[]
}

export function ChatPanel({ tools }: ChatPanelProps) {
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant' | 'system'; content: string; timestamp: Date; toolCalls?: any[] }>>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [currentTask, setCurrentTask] = useState<any>(null)
  const [showPlan, setShowPlan] = useState(false)
  const [plan, setPlan] = useState<any>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage = input
    setMessages(prev => [...prev, { role: 'user', content: userMessage, timestamp: new Date() }])
    setInput('')
    setIsLoading(true)

    try {
      // Create task
      const taskRes = await api.createTask({ title: userMessage, description: userMessage })
      const taskId = taskRes.task_id
      setCurrentTask({ id: taskId, title: userMessage })

      // Plan task
      const planRes = await api.planTask(taskId, userMessage)
      setPlan(planRes.plan)
      setShowPlan(true)

      // Execute task
      await api.executeTask(taskId)

      // Poll for completion
      const result = await pollTaskCompletion(taskId)
      
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: formatResult(result), 
        timestamp: new Date(),
        toolCalls: result.tool_calls || []
      }])
      setCurrentTask(null)
    } catch (error: any) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `Error: ${error.message}`, 
        timestamp: new Date() 
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const pollTaskCompletion = async (taskId: number): Promise<any> => {
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 2000))
      const status = await api.getTaskStatus(taskId)
      if (status.status === 'COMPLETED' || status.status === 'FAILED' || status.status === 'CANCELLED') {
        const task = await api.getTask(taskId)
        return task
      }
      if (status.status === 'WAITING_FOR_APPROVAL') {
        // Would need approval handling here
        break
      }
    }
    return { status: 'TIMEOUT' }
  }

  const formatResult = (task: any) => {
    if (!task.result) return 'Task completed'
    const results = task.result.results || {}
    return Object.entries(results).map(([key, value]) => `${key}: ${JSON.stringify(value, null, 2)}`).join('\n\n')
  }

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h2>Chat</h2>
        <div className="chat-status">
          {currentTask && (
            <span className={cn('status-badge', getStatusColor(currentTask.status?.toLowerCase() || 'created'))}>
              {currentTask.status}
            </span>
          )}
        </div>
      </div>
      
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <Bot size={48} />
            <h3>Welcome to Comet</h3>
            <p>Your personal AI agent. Ask me to:</p>
            <ul>
              <li>Open Notepad and type "Hello"</li>
              <li>Search for files in your workspace</li>
              <li>Open a browser and navigate to a website</li>
              <li>Run tests in your project</li>
              <li>Create a scheduled task</li>
            </ul>
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <div key={idx} className={cn('message', msg.role)}>
            <div className="message-avatar">
              {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
            </div>
            <div className="message-content">
              <div className="message-header">
                <span className="message-role">{msg.role === 'user' ? 'You' : 'Comet'}</span>
                <span className="message-time">{formatRelativeTime(msg.timestamp.toISOString())}</span>
              </div>
              <div className="message-text">{msg.content}</div>
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="tool-calls">
                  {msg.toolCalls.map((tc: any, i: number) => (
                    <div key={i} className="tool-call">
                      <span className="tool-name">{tc.name}</span>
                      <span className="tool-args">{JSON.stringify(tc.arguments)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="message assistant loading">
            <div className="message-avatar"><Bot size={20} /></div>
            <div className="message-content">
              <div className="loading-dots">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {showPlan && plan && (
        <div className="plan-panel">
          <div className="plan-header">
            <h3>Execution Plan</h3>
            <button onClick={() => setShowPlan(false)}>×</button>
          </div>
          <pre>{JSON.stringify(plan, null, 2)}</pre>
        </div>
      )}

      <form onSubmit={handleSubmit} className="chat-input-form">
        <div className="input-wrapper">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Comet to do something..."
            rows={1}
            disabled={isLoading}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
          />
        </div>
        <button 
          type="submit" 
          className="send-button"
          disabled={isLoading || !input.trim()}
        >
          <Send size={20} />
        </button>
      </form>
    </div>
  )
}

// Placeholder components for other panels
export function TaskPanel({ tasks, onRefresh }: any) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Tasks</h2>
        <button className="btn-primary" onClick={() => { /* create task modal */ }}>
          <span>+</span> New Task
        </button>
      </div>
      <div className="tasks-list">
        {tasks.length === 0 ? (
          <div className="empty-state">No tasks yet. Create one to get started.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task: Task) => (
                <tr key={task.id}>
                  <td>{task.task_id}</td>
                  <td>{task.title}</td>
                  <td>
                    <span className={cn('status-badge', getStatusColor(task.status))}>
                      {task.status}
                    </span>
                  </td>
                  <td>{formatRelativeTime(task.created_at)}</td>
                  <td>
                    <button className="btn-icon" onClick={() => { /* view task */ }}>
                      <ChevronDown size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export function ApprovalPanel({ approvals, onRefresh }: any) {
  if (approvals.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header">
          <h2>Approvals</h2>
        </div>
        <div className="empty-state">No pending approvals.</div>
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Approvals ({approvals.length})</h2>
      </div>
      <div className="approvals-list">
        {approvals.map((approval: ApprovalRequest) => (
          <div key={approval.approval_id} className="approval-card">
            <div className="approval-header">
              <h3>{approval.title}</h3>
              <span className={cn('risk-badge', getRiskColor(approval.risk_level))}>
                {approval.risk_level}
              </span>
            </div>
            <p>{approval.description}</p>
            <div className="approval-details">
              <pre>{JSON.stringify(approval.details, null, 2)}</pre>
            </div>
            <div className="approval-actions">
              <button className="btn-danger" onClick={() => api.respondApproval({ approval_id: approval.approval_id, approved: false })}>
                Reject
              </button>
              <button className="btn-primary" onClick={() => api.respondApproval({ approval_id: approval.approval_id, approved: true })}>
                Approve
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ToolsPanel({ tools }: any) {
  const categories = [...new Set(tools.map((t: Tool) => t.category))]
  
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Available Tools ({tools.length})</h2>
      </div>
      <div className="tools-grid">
        {categories.map(category => (
          <div key={category} className="tool-category">
            <h3>{category} ({tools.filter((t: Tool) => t.category === category).length})</h3>
            <div className="tools-list">
              {tools.filter((t: Tool) => t.category === category).map((tool: Tool) => (
                <div key={tool.name} className="tool-card">
                  <div className="tool-header">
                    <span className="tool-name">{tool.name}</span>
                    <span className={cn('risk-badge', getRiskColor(tool.risk_level))}>
                      {tool.risk_level}
                    </span>
                  </div>
                  <p className="tool-desc">{tool.description}</p>
                  <div className="tool-params">
                    {tool.parameters.map((p: any) => (
                      <span key={p.name} className="param-tag">
                        {p.name}: {p.type} {p.required ? '*' : ''}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ActivityPanel() {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Activity</h2>
      </div>
      <div className="activity-timeline">
        <div className="activity-item">
          <div className="activity-time">Just now</div>
          <div className="activity-content">System started</div>
        </div>
      </div>
    </div>
  )
}

export function SettingsPanel() {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Settings</h2>
      </div>
      <div className="settings-form">
        <div className="setting-group">
          <label>Model Provider</label>
          <select defaultValue="gemini">
            <option value="gemini">Gemini</option>
            <option value="nemotron">Nemotron</option>
          </select>
        </div>
        <div className="setting-group">
          <label>Model</label>
          <input type="text" defaultValue="gemini-1.5-flash" />
        </div>
        <div className="setting-group">
          <label>Allowed Directories</label>
          <input type="text" defaultValue="./data/workspace" />
        </div>
        <div className="setting-group">
          <label>Max Tool Calls per Task</label>
          <input type="number" defaultValue="100" />
        </div>
      </div>
    </div>
  )
}