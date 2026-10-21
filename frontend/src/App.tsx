import { useState, useEffect } from 'react'
import { Layout, Sidebar, Header, MainContent, ChatPanel, TaskPanel, ApprovalPanel, ToolsPanel, SettingsPanel, ActivityPanel } from './components'
import { api } from './lib/api'
import type { Task, Tool, ApprovalRequest, HealthStatus } from './types'

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'tasks' | 'approvals' | 'tools' | 'activity' | 'settings'>('chat')
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [tools, setTools] = useState<Tool[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    loadInitialData()
    const interval = setInterval(loadInitialData, 5000)
    return () => clearInterval(interval)
  }, [])

  const loadInitialData = async () => {
    try {
      const [healthRes, toolsRes, tasksRes, approvalsRes] = await Promise.all([
        api.getHealth(),
        api.getTools(),
        api.getTasks(),
        api.getApprovals()
      ])
      setHealth(healthRes)
      setTools(toolsRes)
      setTasks(tasksRes)
      setApprovals(approvalsRes)
    } catch (error) {
      console.error('Failed to load initial data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner"></div>
        <p>Initializing Comet...</p>
      </div>
    )
  }

  return (
    <Layout>
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        health={health}
      />
      <div className="main-area">
        <Header health={health} />
        <MainContent>
          {activeTab === 'chat' && <ChatPanel tools={tools} />}
          {activeTab === 'tasks' && <TaskPanel tasks={tasks} onRefresh={loadInitialData} />}
          {activeTab === 'approvals' && <ApprovalPanel approvals={approvals} onRefresh={loadInitialData} />}
          {activeTab === 'tools' && <ToolsPanel tools={tools} />}
          {activeTab === 'activity' && <ActivityPanel />}
          {activeTab === 'settings' && <SettingsPanel />}
        </MainContent>
      </div>
    </Layout>
  )
}

export default App