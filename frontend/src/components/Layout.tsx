import { ReactNode } from 'react'
import { cn } from '../lib/utils'

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="layout">
      {children}
    </div>
  )
}

interface SidebarProps {
  activeTab: string
  onTabChange: (tab: string) => void
  health: any
}

const tabs = [
  { id: 'chat', label: 'Chat', icon: 'MessageSquare' },
  { id: 'tasks', label: 'Tasks', icon: 'ListChecks' },
  { id: 'approvals', label: 'Approvals', icon: 'ShieldCheck' },
  { id: 'activity', label: 'Activity', icon: 'Activity' },
  { id: 'tools', label: 'Tools', icon: 'Wrench' },
  { id: 'settings', label: 'Settings', icon: 'Settings' },
]

const icons: Record<string, ReactNode> = {
  MessageSquare: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>,
  ListChecks: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 17h18"></path><path d="M3 7h18"></path><path d="M3 12h18"></path><path d="M17 7l2 2 4-4"></path><path d="M9 17l2 2 4-4"></path><path d="M9 12l2 2 4-4"></path></svg>,
  ShieldCheck: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><path d="M9 12l2 2 4-4"></path></svg>,
  Activity: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>,
  Wrench: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14.7 16.2 19 20.5 20.5 19"></path><path d="M15 9 18 12 20 10 17 7"></path><path d="M21 3l-9 9"></path><path d="M14.7 7.8 20 13.1 18.9 14.2"></path></svg>,
  Settings: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>,
}

export function Sidebar({ activeTab, onTabChange, health }: any) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 6v6l4 2"></path>
          </svg>
          <span>Comet</span>
        </div>
        <div className="health-status">
          <span className={cn('status-dot', health?.model_connected ? 'connected' : 'disconnected')} />
          <span className="status-text">
            {health?.model_connected ? 'Model Connected' : 'Model Disconnected'}
          </span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={cn('nav-item', activeTab === tab.id && 'active')}
            onClick={() => onTabChange(tab.id)}
          >
            {icons[tab.icon]}
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="version">v0.1.0</div>
      </div>
    </aside>
  )
}

export function Header({ health }: any) {
  return (
    <header className="header">
      <div className="header-left">
        <h1>Comet - Personal AI Agent</h1>
      </div>
      <div className="header-right">
        <div className="health-indicator">
          <span className={cn('status-dot', health?.model_connected ? 'connected' : 'disconnected')} />
          <span>{health?.model_connected ? 'Model Ready' : 'Model Offline'}</span>
        </div>
      </div>
    </header>
  )
}

export function MainContent({ children }: { children: ReactNode }) {
  return (
    <main className="main-content">
      {children}
    </main>
  )
}