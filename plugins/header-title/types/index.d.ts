export type Limit = { percent: number; resetsAt: string | null }
export type Info = {
  percent: number | null
  model: string
  cwd: string
  git: string | null
  limit: Limit | null
  week: Limit | null
  at: number
}

// A Bash call by its tool_use_id; taskId is set once it runs in the background, agentId when a subagent made it.
export type Shell = { id: string; taskId: string | null; label: string; agentId: string | null }

// How many ultracode rows of which session's transcript the band already follows.
export type UltracodeSeen = { sessionId: string; rows: number }

declare module 'claude-code' {
  interface PluginState {
    'header-title': {
      name: string | null
      info: Info | null
      agents: string[]
      shells: Shaped<Shell[]>
      effort: string | null
      ultracode: boolean
      ultracodeSeen: UltracodeSeen | null
    }
  }
}
