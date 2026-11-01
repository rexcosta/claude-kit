import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, SessionRateLimit } from 'claude-code'

import type { Info, Limit, Shell, UltracodeSeen } from '../types'

// The session's /rename name; null until it has one.
const name = atom({ plugin: 'header-title', key: 'name' } as const, null as string | null)
// What the old status line showed, refreshed at session start and after each turn.
const info = atom({ plugin: 'header-title', key: 'info' } as const, null as Info | null)
// Ids of the subagents whose turn is running, so the band can say it waits on them.
const agents = atom({ plugin: 'header-title', key: 'agents' } as const, [] as string[])
// Bash calls running now, and the ones moved to the background until their notice arrives or their
// agent ends. The shape drops lists stored before shells kept their agent.
const shells = atom({ plugin: 'header-title', key: 'shells' } as const, [] as Shell[], { shape: 'with-agent' })
// The main loop's effort as its last turn's first request carried it; null before one, or for a model without effort.
const effort = atom({ plugin: 'header-title', key: 'effort' } as const, null as string | null)
// Whether ultracode is on, from the settings, an /effort answer or a later transcript row.
const ultracode = atom({ plugin: 'header-title', key: 'ultracode' } as const, false)
const ultracodeSeen = atom({ plugin: 'header-title', key: 'ultracodeSeen' } as const, null as UltracodeSeen | null)
const DEFAULT_TITLE = 'Unnamed session'
const MAX_SHELLS = 3

// The branch, or the worktree's name when the folder is a linked worktree; null outside git.
// Absolute paths: in a subfolder git prints --git-dir absolute and --git-common-dir relative.
const readGit = async ($: EngineInterface) => {
  const { exitCode, stdout } = await $.process.run([
    'git', 'rev-parse', '--abbrev-ref', 'HEAD', '--path-format=absolute', '--git-dir', '--git-common-dir',
    '--show-toplevel',
  ])

  if (exitCode !== 0) {
    return null
  }

  const [branch = '', gitDir, commonDir, top = ''] = stdout.trim().split('\n')
  const label = branch === 'HEAD' ? 'detached' : branch

  return gitDir === commonDir ? `⎇ ${label}` : `worktree ${top.split('/').pop()} (${label})`
}

const toLimit = (window: SessionRateLimit | undefined) =>
  window ? { percent: window.percentUsed, resetsAt: window.resetsAt ?? null } : null

const refreshInfo = async ($: EngineInterface) => {
  const [{ context, rateLimits }, model, cwd, git, at] = await Promise.all([
    $.session.usage(),
    $.session.model(),
    $.session.cwd(),
    readGit($).catch(() => null),
    $.clock.now(),
  ])
  const limit = toLimit(rateLimits.find(one => one.kind === 'five_hour'))
  const week = toLimit(rateLimits.find(one => one.kind === 'seven_day'))
  await update($, info, () => ({ percent: context.percent ?? null, model, cwd, git, limit, week, at }))
}

// No API returns the session's name or whether ultracode is on: /rename writes the name to the
// transcript as a {"type":"custom-title","customTitle":"…"} row, ultracode's reminders write
// {"type":"ultra_effort_enter"} (on, or still on) and {"type":"ultra_effort_exit"} attachment rows,
// and the last row of each is current.
const NAME_PATTERN = '"customTitle":"([^"\\\\]|\\\\.)*"'
const ULTRACODE_PATTERN = '"type":"ultra_effort_(enter|exit)"'

const parseName = (row: string) => {
  try {
    return (JSON.parse(`{${row}}`) as { customTitle: string }).customTitle
  } catch {
    return undefined
  }
}

// The last rename row's name (null when there is none, undefined when it does not parse), whether
// the last ultracode row is on and how many there are; undefined when the search failed.
const readTranscript = async ($: EngineInterface) => {
  const [id, configDir, home] = await Promise.all([
    $.session.id(),
    $.env.get('CLAUDE_CONFIG_DIR'),
    $.env.get('HOME'),
  ])
  // grep, not $.fs.read: transcripts run to tens of MB.
  const { exitCode, stdout } = await $.process.run([
    'grep', '-r', '-h', '-o', '-E', '-e', NAME_PATTERN, '-e', ULTRACODE_PATTERN, `--include=${id}.jsonl`,
    `${configDir ?? `${home ?? ''}/.claude`}/projects`,
  ])
  const rows = stdout.split('\n').filter(Boolean)

  // grep exits 1 when nothing matched, and 2 when it could not read a file under the folder: with
  // rows printed, it read the session's own.
  if (rows.length === 0 && exitCode !== 1) {
    return undefined
  }

  const lastName = rows.filter(row => row.startsWith('"customTitle"')).pop()
  const ultracodeRows = rows.filter(row => row.startsWith('"type"'))

  return {
    sessionId: id,
    name: lastName ? parseName(lastName) : null,
    isUltracode: ultracodeRows[ultracodeRows.length - 1] === '"type":"ultra_effort_enter"',
    ultracodeRows: ultracodeRows.length,
  }
}

// A failed search keeps what the band has. Ultracode follows only rows written after the ones it
// already follows: /effort answers before the next prompt writes its row, and a new process (a
// restart, a resume) starts ultracode from the settings, whatever an earlier one wrote.
const refreshTranscript = async ($: EngineInterface) => {
  const found = await readTranscript($).catch(() => undefined)

  if (found === undefined) {
    return
  }

  const { name: given, sessionId, isUltracode, ultracodeRows } = found
  const seen = await read($, ultracodeSeen)
  const isOtherSession = seen === null || seen.sessionId !== sessionId

  if (given !== undefined) {
    await update($, name, () => given)
  }

  if (isOtherSession || ultracodeRows > seen.rows) {
    const isOn = isOtherSession
      ? (await $.settings.read({ key: 'ultracode' }).catch(() => undefined)) === true
      : isUltracode
    await Promise.all([
      update($, ultracode, () => isOn),
      update($, ultracodeSeen, () => ({ sessionId, rows: ultracodeRows })),
    ])
  }
}

// Cuts a folder name past 15 characters in the middle: sdafnsadsadfsadfsadfsadfsf → sdafns...sadfsf
const clip = (name: string) => (name.length > 15 ? `${name.slice(0, 6)}...${name.slice(-6)}` : name)

// Keeps the last two folders: /Users/me/Projects/my-app → ../Projects/my-app
const shorten = (path: string) => {
  const parts = path.split('/').filter(Boolean).map(clip)

  return parts.length > 2 ? `../${parts.slice(-2).join('/')}` : `/${parts.join('/')}`
}

const describeContext = (percent: number | null) =>
  percent === null ? 'ctx: --' : `ctx: ${percent}% used`

const describeReset = (resetsAt: string | null, at: number) => {
  if (resetsAt === null) {
    return ''
  }

  const minutes = Math.max(0, Math.round((Date.parse(resetsAt) - at) / 60000))
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor(minutes / 60) % 24

  return days > 0
    ? `  |  resets in ${days}d ${hours}h`
    : `  |  resets in ${hours}h ${minutes % 60}m`
}

// The usage call keeps the last response's figures: past its reset time a window reads as reset.
const isReset = (limit: Limit, at: number) => limit.resetsAt !== null && Date.parse(limit.resetsAt) <= at

const describeAgents = (count: number) => (count === 1 ? '1 agent' : `${count} agents`)

const describeModel = (model: string, level: string | null, isUltracode: boolean) =>
  [model, level && `· ${level}`, level === 'max' && '💪', isUltracode && '🤔'].filter(Boolean).join(' ')

// What /effort answers when it changed something; another answer, or a new wording, waits for the next request.
const EFFORT_SET = /^Set effort level to (low|medium|high|xhigh|max)\b/
// The picker answers the level first: 'Set effort level to max …: … · Ultracode on'.
const ULTRACODE_SET = /(?:^|· )Ultracode (on|off)\b/

export const register: Register = on => {
  let ticker: { cancel: () => void } | undefined
  let calls = 0

  on('session.start', async ($, e, next) => {
    await Promise.all([refreshTranscript($), refreshInfo($)])
    // Keeps the reset countdown moving between turns.
    ticker?.cancel()
    ticker = $.clock.every(60_000, () => void refreshInfo($).catch(() => {}))

    return next(e)
  })

  on('turn.start', async ($, e, next) => {
    const { agentId } = e

    if (agentId !== undefined) {
      await update($, agents, all => (all.includes(agentId) ? all : [...all, agentId]))
    }

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    const { agentId } = e

    // The engine stops an agent's background shells when it ends, and sends no notice for them.
    if (agentId !== undefined) {
      await update($, agents, all => all.filter(one => one !== agentId))
      await update($, shells, all => all.filter(one => one.agentId !== agentId))
    }

    await Promise.all([refreshTranscript($), refreshInfo($)])

    return done
  })

  // No API returns the session's effort: the first request of each main loop turn carries it,
  // before a skill's own effort can raise the rest of the turn.
  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined && e.index === 0) {
      const level = e.effort === undefined ? null : String(e.effort)

      if ((await read($, effort)) !== level) {
        await update($, effort, () => level)
      }
    }

    return yield* next(e)
  })

  // The built-in /rename runs as usual; the band takes the name from its args, or from the
  // transcript when a bare /rename made one up.
  on('command.run', { command: 'rename' }, async ($, e, next) => {
    const done = await next(e)
    const given = e.args.trim()
    await (given ? update($, name, () => given) : refreshTranscript($))

    return done
  })

  on('command.run', { command: 'effort' }, async ($, e, next) => {
    const done = await next(e)
    const level = EFFORT_SET.exec(done.text ?? '')?.[1]
    const toggle = ULTRACODE_SET.exec(done.text ?? '')?.[1]

    if (level) {
      await update($, effort, () => level)
    }

    // Its row comes with the next prompt: the rows written so far are older than this answer.
    if (toggle) {
      const found = await readTranscript($).catch(() => undefined)
      await update($, ultracode, () => toggle === 'on')

      if (found !== undefined) {
        await update($, ultracodeSeen, () => ({ sessionId: found.sessionId, rows: found.ultracodeRows }))
      }
    }

    return done
  })

  // A foreground call shows while it runs; one that ends in the background (run_in_background,
  // or ctrl+b) stays under its task id.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const id = e.tool_use_id ?? `call-${++calls}`
    const label = e.description?.trim() || e.command
    const agentId = e.agentId ?? null

    if (e.run_in_background !== true) {
      await update($, shells, all => [...all, { id, taskId: null, label, agentId }])
    }

    const ran = await next(e).catch(async (error: unknown) => {
      await update($, shells, all => all.filter(one => one.id !== id))
      throw error
    })
    const taskId = ran.deny === undefined && ran.isError !== true ? ran.result.backgroundTaskId : undefined
    await update($, shells, all => [
      ...all.filter(one => one.id !== id),
      ...(taskId ? [{ id, taskId, label, agentId }] : []),
    ])

    return ran
  })

  // A background shell's notice (completed, failed or killed) names its <task-id>.
  on('prompt.submit', async ($, e, next) => {
    const ended = [...e.text.matchAll(/<task-id>([^<]+)<\/task-id>/g)].map(([, taskId]) => taskId)

    if (ended.length > 0) {
      await update($, shells, all => all.filter(one => one.taskId === null || !ended.includes(one.taskId)))
    }

    return next(e)
  })

  on('tool.call', { tool: 'TaskStop' }, async ($, e, next) => {
    const ran = await next(e)
    const taskId = e.task_id ?? e.shell_id

    if (ran.deny === undefined && ran.isError !== true && taskId) {
      await update($, shells, all => all.filter(one => one.taskId !== taskId))
    }

    return ran
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const title = await read($, name)
    const current = await read($, info)
    const running = (await read($, agents)).length
    const stored = await read($, shells)
    const level = await read($, effort)
    const isUltracode = await read($, ultracode)
    // This turn's calls first, so background shells never push them into `+N more`.
    const allShells = [...stored.filter(one => one.taskId === null), ...stored.filter(one => one.taskId !== null)]

    if (e.props.hasSurvey) {
      return next(e)
    }

    const { Box, Text } = $.ui.resolve(e)
    const used = current?.percent ?? 0
    // Bold past 50%, red past 70%: the context and the 5h window alike.
    const usage = (text: string, percent: number) =>
      percent > 70 ? (
        <Text bold color="red">
          {text}
        </Text>
      ) : (
        <Text dimColor bold={percent > 50}>
          {text}
        </Text>
      )
    // The week has its own scale: bold red past 80%; at 100% extra usage is billed.
    const weekUsage = (percent: number) =>
      percent >= 100 ? (
        <Text bold color="red">
          week: limit reached and now paying
        </Text>
      ) : percent > 80 ? (
        <Text bold color="red">
          {`week: ${percent}% used`}
        </Text>
      ) : (
        <Text dimColor>{`week: ${percent}% used`}</Text>
      )
    const limitLine =
      current?.limit &&
      (isReset(current.limit, current.at) ? (
        <Text dimColor>5h: reset</Text>
      ) : (
        <Box>
          {usage(`5h: ${current.limit.percent}% used`, current.limit.percent)}
          <Text dimColor>{describeReset(current.limit.resetsAt, current.at)}</Text>
        </Box>
      ))
    const weekLine =
      current?.week &&
      (isReset(current.week, current.at) ? (
        <Text dimColor>week: reset</Text>
      ) : (
        <Box>
          {weekUsage(current.week.percent)}
          <Text dimColor>{describeReset(current.week.resetsAt, current.at)}</Text>
        </Box>
      ))
    // A row each for the top margin, title, path, context, the two windows, the status and the shells.
    const rows =
      3 +
      (current ? 2 : 0) +
      (limitLine ? 1 : 0) +
      (weekLine ? 1 : 0) +
      Math.min(allShells.length, MAX_SHELLS) +
      (allShells.length > MAX_SHELLS ? 1 : 0)
    // Short of rows, the band drops its top margin and puts the two windows on one row.
    const isTight = rows > e.props.maxRows
    const isMerged = isTight && Boolean(limitLine) && Boolean(weekLine)

    return (
      <Box flexDirection="column" marginTop={isTight ? 0 : 1}>
        {title ? (
          <Text bold color="cyan" wrap="truncate-end">
            {title}
          </Text>
        ) : (
          <Box>
            <Text bold color="cyan">
              {DEFAULT_TITLE}
            </Text>
            <Text dimColor wrap="truncate-end">{'  run /rename <name> to set one'}</Text>
          </Box>
        )}
        {current && (
          <Text dimColor wrap="truncate-end">
            {current.git ? `${shorten(current.cwd)}  |  ${current.git}` : shorten(current.cwd)}
          </Text>
        )}
        {current && (
          <Box>
            {usage(describeContext(current.percent), used)}
            <Text dimColor wrap="truncate-end">
              {`  |  ${describeModel(current.model, level, isUltracode)}`}
            </Text>
          </Box>
        )}
        {isMerged ? (
          <Box>
            {limitLine}
            <Text dimColor>{'  ·  '}</Text>
            {weekLine}
          </Box>
        ) : (
          limitLine
        )}
        {!isMerged && weekLine}
        {e.props.isWorking ? (
          <Text color="yellow">
            {running > 0 ? `● working · ${describeAgents(running)} running` : '● working'}
          </Text>
        ) : running > 0 ? (
          <Text color="magenta">◐ waiting for {describeAgents(running)}</Text>
        ) : (
          <Text color="green">○ waiting for input</Text>
        )}
        {/* Yellow runs in this turn, magenta in the background. */}
        {allShells.slice(0, MAX_SHELLS).map(one => (
          <Text key={one.id} color={one.taskId ? 'magenta' : 'yellow'} wrap="truncate-end">
            {one.taskId ? `⚙ ${one.label}  · background` : `⚙ ${one.label}`}
          </Text>
        ))}
        {allShells.length > MAX_SHELLS && (
          <Text dimColor>{`  +${allShells.length - MAX_SHELLS} more`}</Text>
        )}
      </Box>
    )
  })
}
