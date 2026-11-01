import { expect, mock, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

const BAND = {
  plugin: 'header-title',
  component: 'AbovePrompt',
  surface: 'terminal',
  props: { hasSurvey: false, isWorking: false },
} as const

type Git = { exitCode: number; stdout: string }
type RateLimit = { kind: string; percentUsed: number; resetsAt?: string }

// The engine the band runs on, its clock at `now` when given. A test changes what the engine answers
// through `state`; greps and renames list each transcript search and each /rename.
const setup = ($: Parameters<TestBody>[0], on: Parameters<TestBody>[1], now?: number) => {
  const state = {
    cwd: '/projects/a',
    percent: 10,
    rateLimits: [] as RateLimit[],
    git: (_argv: readonly string[]): Git => ({ exitCode: 128, stdout: '' }),
    transcript: '',
    grepExitCode: undefined as number | undefined,
    greps: [] as string[][],
    renames: [] as string[],
    commandText: '',
    sessionId: 'sess-1',
    settingsUltracode: false,
  }
  mock.store(on)

  if (now === undefined) {
    mock.clock(on)
  } else {
    mock.clock(on, { now })
  }

  on('session.id', () => ({ value: state.sessionId }))
  on('settings.read', () => ({ value: state.settingsUltracode ? { ultracode: true } : {} }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : undefined }))
  on('session.cwd', () => ({ value: state.cwd }))
  on('session.model', () => ({ value: 'Opus 5.5' }))
  on('session.usage', () => ({
    value: { startedAt: 0, context: { window: 200000, percent: state.percent }, rateLimits: state.rateLimits },
  }))
  on('process.run', (_, e) => {
    const isGit = e.argv[0] === 'git'

    if (!isGit) {
      state.greps.push([...e.argv])
    }

    // As grep -o prints them: each match of the -e patterns, in the order the transcript holds them.
    const patterns = e.argv.filter((_, i) => e.argv[i - 1] === '-e').map(pattern => `(?:${pattern})`)
    const matches = isGit ? [] : [...state.transcript.matchAll(new RegExp(patterns.join('|'), 'g'))].map(([match]) => match)
    const { exitCode, stdout } = isGit
      ? state.git(e.argv)
      : { exitCode: state.grepExitCode ?? (matches.length > 0 ? 0 : 1), stdout: matches.map(match => `${match}\n`).join('') }

    return { value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('command.run', (_, e) => {
    state.renames.push(e.args)

    return { text: state.commandText }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('turn.step', async function* (_, e) {
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: null, usage: null }
  })

  const start = () => $.session.start({ cwd: state.cwd, surface: 'terminal', isInteractive: true })

  // One model request: the first of a main loop turn unless told, with no effort for a model that takes none.
  const step = async (effort?: 'low' | 'xhigh' | 'max' | number, { agentId, index = 0 }: { agentId?: string; index?: number } = {}) => {
    const stream = $.turn.step({
      turnId: 't1',
      index,
      model: 'claude-opus-5-5',
      messageCount: 1,
      ...(effort === undefined ? {} : { effort }),
      ...(agentId === undefined ? {} : { agentId }),
    })

    for await (const _ of stream) {
      // The bottom answers without chunks.
    }
  }

  const modelLine = async () => {
    const ui = await $.ui.mount(BAND)
    const found = (await ui.find({ type: 'Text', text: /Opus/ }))?.text
    await ui.unmount()

    return found
  }

  const title = async () => {
    const ui = await $.ui.mount(BAND)
    const found = (await ui.find({ type: 'Text', text: /^(?!\/|ctx:|  \||  run|● |○ )/ }))?.text
    await ui.unmount()

    return found
  }

  const shellLines = async () => {
    const ui = await $.ui.mount(BAND)
    const found = await ui.findAll({ type: 'Text', text: /^⚙|^  \+/ })
    await ui.unmount()

    return found.map(one => `${one.props.color ?? 'dim'}: ${one.text}`)
  }

  return { state, start, step, title, modelLine, shellLines }
}

type Drawn = { props?: Record<string, unknown>; children?: unknown[] }

const textOf = (node: unknown): string =>
  typeof node === 'string'
    ? node
    : Array.isArray(node)
      ? node.map(textOf).join('')
      : node !== null && typeof node === 'object'
        ? ((node as Drawn).children ?? []).map(textOf).join('')
        : ''

// The band's rows as text: an empty row for each row of top margin, then one row per child of its column.
const rowsOf = (tree: unknown) => {
  const { props = {}, children = [] } = tree as Drawn
  const drawn = children.flat().filter(child => typeof child === 'string' || (child !== null && typeof child === 'object'))

  return [...Array.from({ length: Number(props.marginTop ?? 0) }, () => ''), ...drawn.map(textOf)]
}

test('the band shows the last /rename name in the transcript, and Unnamed session without one', async ($, on) => {
  const { state, start, title } = setup($, on)

  await start()
  expect(await title()).toBe('Unnamed session')
  expect(state.greps[0]?.slice(-2)).toEqual(['--include=sess-1.jsonl', '/home/me/.claude/projects'])

  state.transcript = '"customTitle":"Old name"\n"customTitle":"Search \\"v2\\" refactor"\n'
  await start()
  expect(await title()).toBe('Search "v2" refactor')
})

test('/rename updates the band at once, from its args or, bare, from the transcript', async ($, on) => {
  const { state, start, title } = setup($, on)
  await start()

  await $.command.run({ command: 'rename', args: '  Search refactor ' })
  expect(state.renames).toEqual(['  Search refactor '])
  expect(await title()).toBe('Search refactor')

  state.transcript = '"customTitle":"Search refactor"\n"customTitle":"made-up-name"\n'
  await $.command.run({ command: 'rename', args: '' })
  expect(await title()).toBe('made-up-name')
})

test('a failed transcript search keeps the name the band has', async ($, on) => {
  const { state, start, title } = setup($, on)
  state.transcript = '"customTitle":"Search refactor"\n'
  await start()
  expect(await title()).toBe('Search refactor')

  // grep exits 2 when it could not read a file under projects: with nothing printed, the name is unknown.
  state.transcript = ''
  state.grepExitCode = 2
  await start()
  expect(await title()).toBe('Search refactor')

  // Exit 2 with rows printed: the last one stands.
  state.transcript = '"customTitle":"Search refactor"\n"customTitle":"Login screen"\n'
  await start()
  expect(await title()).toBe('Login screen')

  // A row that does not parse is a failed search too.
  state.transcript = '"customTitle":"bad \\x escape"\n'
  state.grepExitCode = undefined
  await start()
  expect(await title()).toBe('Login screen')

  // Exit 1, nothing matched: the session has no name.
  state.transcript = ''
  await start()
  expect(await title()).toBe('Unnamed session')
})

test('the context reads bold past 50% and red past 70%', async ($, on) => {
  const { state, start } = setup($, on)

  const ctx = async () => {
    const ui = await $.ui.mount(BAND)
    const found = await ui.find({ type: 'Text', text: /^ctx:/ })
    await ui.unmount()

    return { text: found?.text, isBold: found?.props.bold === true, color: found?.props.color }
  }

  for (const [value, isBold, color] of [[42, false, undefined], [50, false, undefined], [51, true, undefined], [70, true, undefined], [71, true, 'red']] as const) {
    state.percent = value
    await start()
    expect(await ctx()).toEqual({ text: `ctx: ${value}% used`, isBold, color })
  }
})

// An ultracode reminder as the transcript holds it; its own "type":"attachment" is no match.
const ultracodeRow = (type: 'ultra_effort_enter' | 'ultra_effort_exit') =>
  `{"parentUuid":"p1","isSidechain":false,"attachment":{"type":"${type}"},"type":"attachment","uuid":"u1"}\n`

test("the model adds the effort of the main loop turn's first request, and 💪 at max", async ($, on) => {
  const { start, step, modelLine } = setup($, on)
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5')

  await step('xhigh')
  expect(await modelLine()).toBe('  |  Opus 5.5 · xhigh')

  // A subagent runs at its own effort, and a skill's effort raises only the rest of its turn.
  await step('low', { agentId: 'a1' })
  await step('max', { index: 3 })
  expect(await modelLine()).toBe('  |  Opus 5.5 · xhigh')

  await step('max')
  expect(await modelLine()).toBe('  |  Opus 5.5 · max 💪')

  // A model that takes no effort; a number stays as the request carried it.
  await step()
  expect(await modelLine()).toBe('  |  Opus 5.5')
  await step(42)
  expect(await modelLine()).toBe('  |  Opus 5.5 · 42')
})

test('🤔 follows the ultracode rows the session writes, found by the same search as the name', async ($, on) => {
  const { state, start, step, title, modelLine } = setup($, on)
  await start()
  await step('max')

  state.transcript = `{"type":"custom-title","customTitle":"Login screen","sessionId":"sess-1"}\n${ultracodeRow('ultra_effort_enter')}`
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5 · max 💪 🤔')
  expect(await title()).toBe('Login screen')
  expect(state.greps).toHaveLength(2)

  // Still on, then off.
  state.transcript += ultracodeRow('ultra_effort_enter')
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5 · max 💪 🤔')

  state.transcript += ultracodeRow('ultra_effort_exit')
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5 · max 💪')
})

test("a new process starts ultracode from the settings, not from an earlier process's rows", async ($, on) => {
  const { state, start, modelLine } = setup($, on)
  // A resumed session that ended with ultracode on: a toggle never outlives its process.
  state.transcript = ultracodeRow('ultra_effort_enter')
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5')

  // Its first prompt writes the exit row.
  state.transcript += ultracodeRow('ultra_effort_exit')
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5')

  // Another session, with ultracode on in the settings.
  state.settingsUltracode = true
  state.sessionId = 'sess-2'
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5 🤔')
})

test('a failed transcript search, or a name row that does not parse, keeps ultracode right', async ($, on) => {
  const { state, start, title, modelLine } = setup($, on)
  await start()
  state.transcript = ultracodeRow('ultra_effort_enter')
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5 🤔')

  state.transcript = ''
  state.grepExitCode = 2
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5 🤔')

  // Rows printed: the session's own file was read, whatever else grep could not read.
  state.transcript = `"customTitle":"Login screen"\n${ultracodeRow('ultra_effort_enter')}${ultracodeRow('ultra_effort_exit')}`
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5')
  expect(await title()).toBe('Login screen')

  state.grepExitCode = undefined
  state.transcript += `"customTitle":"bad \\x escape"\n${ultracodeRow('ultra_effort_enter')}`
  await start()
  expect(await modelLine()).toBe('  |  Opus 5.5 🤔')
  expect(await title()).toBe('Login screen')
})

test('/effort changes the band at once when its answer says so, until a later row', async ($, on) => {
  const { state, start, step, modelLine } = setup($, on)
  await start()
  await step('xhigh')

  const effort = async (args: string, text: string) => {
    state.commandText = text
    await $.command.run({ command: 'effort', args })

    return modelLine()
  }
  const complete = (agentId?: string) =>
    $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer', ...(agentId ? { agentId } : {}) })

  expect(await effort('max', 'Set effort level to max (this session only): Maximum capability with deepest reasoning.')).toBe(
    '  |  Opus 5.5 · max 💪',
  )
  expect(await effort('ultracode', 'Ultracode on (this session only): standing orchestration. Effort stays max.')).toBe(
    '  |  Opus 5.5 · max 💪 🤔',
  )

  // Its row comes with the next prompt: a search before it, as a subagent ends, keeps the answer.
  await complete('a1')
  expect(await modelLine()).toBe('  |  Opus 5.5 · max 💪 🤔')

  state.transcript = ultracodeRow('ultra_effort_enter')
  await complete()
  expect(await modelLine()).toBe('  |  Opus 5.5 · max 💪 🤔')

  // Off in the middle of a turn: its end still finds the enter row last.
  expect(await effort('ultracode off', 'Ultracode off. Effort stays max.')).toBe('  |  Opus 5.5 · max 💪')
  await complete()
  expect(await modelLine()).toBe('  |  Opus 5.5 · max 💪')

  // The picker answers the level first and ultracode after it.
  expect(await effort('', 'Set effort level to high (this session only): Deeper reasoning. · Ultracode on')).toBe(
    '  |  Opus 5.5 · high 🤔',
  )

  // Answers that changed nothing, or do not say what changed.
  expect(await effort('ultracode off', "Ultracode isn't available on claude-haiku-4-5. Valid options are: low, high")).toBe(
    '  |  Opus 5.5 · high 🤔',
  )
  expect(await effort('auto', 'Effort level set to auto')).toBe('  |  Opus 5.5 · high 🤔')
  expect(await effort('max', 'Failed to set effort level: busy')).toBe('  |  Opus 5.5 · high 🤔')
})

test('the path line adds the branch, or the worktree, and nothing outside git', async ($, on) => {
  const { state, start } = setup($, on)
  const top = '/Users/me/Documents/Projects/my-app'
  state.cwd = top

  const pathLine = async () => {
    await start()
    const ui = await $.ui.mount(BAND)
    const found = await ui.find({ type: 'Text', text: /^\.\.\// })
    const model = await ui.find({ type: 'Text', text: /Opus/ })
    await ui.unmount()
    expect(model?.text).toBe('  |  Opus 5.5')

    return found?.text
  }

  state.git = () => ({ exitCode: 0, stdout: `main\n${top}/.git\n${top}/.git\n${top}\n` })
  expect(await pathLine()).toBe('../Projects/my-app  |  ⎇ main')

  state.git = () => ({ exitCode: 0, stdout: 'feat/x\n/repo/.git/worktrees/wt-feat\n/repo/.git\n/Users/me/wt-feat\n' })
  expect(await pathLine()).toBe('../Projects/my-app  |  worktree wt-feat (feat/x)')

  state.git = () => ({ exitCode: 128, stdout: '' })
  expect(await pathLine()).toBe('../Projects/my-app')
})

test('a subfolder of the main checkout reads as its branch, not as a worktree', async ($, on) => {
  const { state, start } = setup($, on)
  state.cwd = '/Users/me/repo/Apps'
  // As git answers in a subfolder: --git-common-dir comes back relative, unless an earlier
  // --path-format=absolute covers it.
  state.git = argv => {
    const flag = argv.indexOf('--path-format=absolute')
    const commonDir = flag !== -1 && flag < argv.indexOf('--git-common-dir') ? '/Users/me/repo/.git' : '../.git'

    return { exitCode: 0, stdout: `main\n/Users/me/repo/.git\n${commonDir}\n/Users/me/repo\n` }
  }

  await start()
  const ui = await $.ui.mount(BAND)
  expect((await ui.find({ type: 'Text', text: /^\.\.\// }))?.text).toBe('../repo/Apps  |  ⎇ main')
  await ui.unmount()
})

test('the path line cuts a long folder name in the middle', async ($, on) => {
  const { state, start } = setup($, on)

  const pathLine = async () => {
    await start()
    const ui = await $.ui.mount(BAND)
    const found = await ui.find({ type: 'Text', text: /^(\.\.)?\// })
    await ui.unmount()

    return found?.text
  }

  state.cwd = '/Users/me/sdafnsadsadfsadfsadfsafasdfasdfsadfasdfsadfsf/my-app-ios'
  expect(await pathLine()).toBe('../sdafns...sadfsf/my-app-ios')

  // Exactly 15 characters stays whole; a short path is clipped too.
  state.cwd = '/Users/me/fifteen-chars-a/my-app-ios'
  expect(await pathLine()).toBe('../fifteen-chars-a/my-app-ios')
  state.cwd = '/sdafnsadsadfsadfsadfsafasdfasdfsadfasdfsadfsf'
  expect(await pathLine()).toBe('/sdafns...sadfsf')
})

test('the title, its hint, the path and the model cut at the edge instead of wrapping', async ($, on) => {
  const { start } = setup($, on)
  await start()

  const wraps = async () => {
    const ui = await $.ui.mount(BAND)
    const found = await ui.findAll({ type: 'Text', text: /^(Login screen|  run \/rename|\/projects\/a|  \|  Opus)/ })
    await ui.unmount()

    return found.map(one => `${one.text}: ${String(one.props.wrap)}`)
  }

  expect(await wraps()).toEqual([
    '  run /rename <name> to set one: truncate-end',
    '/projects/a: truncate-end',
    '  |  Opus 5.5: truncate-end',
  ])

  await $.command.run({ command: 'rename', args: 'Login screen' })
  expect(await wraps()).toEqual(['Login screen: truncate-end', '/projects/a: truncate-end', '  |  Opus 5.5: truncate-end'])
})

test('the 5h line reads like the context, with the time to its reset', async ($, on) => {
  const { state, start } = setup($, on, Date.parse('2026-10-22T10:00:00Z'))
  state.rateLimits = [{ kind: 'five_hour', percentUsed: 73, resetsAt: '2026-10-22T12:14:00Z' }]

  await start()
  const ui = await $.ui.mount(BAND)
  const limit = await ui.find({ type: 'Text', text: /^5h:/ })
  expect(limit?.text).toBe('5h: 73% used')
  expect(limit?.props.color).toBe('red')
  expect((await ui.find({ type: 'Text', text: /resets in/ }))?.text).toBe('  |  resets in 2h 14m')
  await ui.unmount()
})

test('the week line goes bold red past 80% and says paying at 100%', async ($, on) => {
  const { state, start } = setup($, on, Date.parse('2026-10-22T10:00:00Z'))

  const week = async (percentUsed: number) => {
    state.rateLimits = [
      { kind: 'five_hour', percentUsed: 20, resetsAt: '2026-10-22T12:14:00Z' },
      { kind: 'seven_day', percentUsed, resetsAt: '2026-10-25T13:30:00Z' },
    ]
    await start()
    const ui = await $.ui.mount(BAND)
    const found = await ui.find({ type: 'Text', text: /^week:/ })
    const reset = await ui.find({ type: 'Text', text: /resets in \d+d/ })
    await ui.unmount()

    return { text: found?.text, isBold: found?.props.bold === true, color: found?.props.color, reset: reset?.text }
  }

  for (const [value, text, isBold, color] of [
    [42, 'week: 42% used', false, undefined],
    [80, 'week: 80% used', false, undefined],
    [81, 'week: 81% used', true, 'red'],
    [100, 'week: limit reached and now paying', true, 'red'],
    [104, 'week: limit reached and now paying', true, 'red'],
  ] as const) {
    expect(await week(value)).toEqual({ text, isBold, color, reset: '  |  resets in 3d 3h' })
  }
})

test('a window past its reset reads as reset, not as the last response left it', async ($, on) => {
  const { state, start } = setup($, on, Date.parse('2026-10-22T13:00:00Z'))

  const windows = async (weekResetsAt: string) => {
    // The figures the last response reported, from before the 5h window reset at 12:14.
    state.rateLimits = [
      { kind: 'five_hour', percentUsed: 96, resetsAt: '2026-10-22T12:14:00Z' },
      { kind: 'seven_day', percentUsed: 100, resetsAt: weekResetsAt },
    ]
    await start()
    const ui = await $.ui.mount(BAND)
    const found = await ui.findAll({ type: 'Text', text: /^(5h|week):|resets in/ })
    await ui.unmount()

    return found.map(one => `${one.props.color ?? (one.props.dimColor === true ? 'dim' : 'plain')}: ${one.text}`)
  }

  expect(await windows('2026-10-25T13:00:00Z')).toEqual([
    'dim: 5h: reset',
    'red: week: limit reached and now paying',
    'dim:   |  resets in 3d 0h',
  ])

  // The minute of the reset itself counts as past it.
  expect(await windows('2026-10-22T13:00:00Z')).toEqual(['dim: 5h: reset', 'dim: week: reset'])
})

test('a band short of rows drops its top margin and puts both windows on one row', async ($, on) => {
  const { state, start } = setup($, on, Date.parse('2026-10-22T10:00:00Z'))
  state.rateLimits = [
    { kind: 'five_hour', percentUsed: 20, resetsAt: '2026-10-22T12:14:00Z' },
    { kind: 'seven_day', percentUsed: 42, resetsAt: '2026-10-25T13:30:00Z' },
  ]
  await start()

  const rows = async (maxRows: number) => {
    const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, maxRows } })
    const drawn = await ui.drawn()
    await ui.unmount()

    return rowsOf(drawn)
  }

  // The whole band takes 7 rows.
  expect(await rows(7)).toEqual([
    '',
    'Unnamed session  run /rename <name> to set one',
    '/projects/a',
    'ctx: 10% used  |  Opus 5.5',
    '5h: 20% used  |  resets in 2h 14m',
    'week: 42% used  |  resets in 3d 3h',
    '○ waiting for input',
  ])
  expect(await rows(6)).toEqual([
    'Unnamed session  run /rename <name> to set one',
    '/projects/a',
    'ctx: 10% used  |  Opus 5.5',
    '5h: 20% used  |  resets in 2h 14m  ·  week: 42% used  |  resets in 3d 3h',
    '○ waiting for input',
  ])
})

test('the last line says working during a turn and waiting for input otherwise', async ($, on) => {
  const { start } = setup($, on)
  await start()

  for (const [isWorking, text] of [[true, '● working'], [false, '○ waiting for input']] as const) {
    const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, isWorking } })
    expect((await ui.find({ type: 'Text', text: /^[●○] / }))?.text).toBe(text)
    await ui.unmount()
  }
})

test('an unnamed session hints at /rename; a named one shows its name alone', async ($, on) => {
  const { start } = setup($, on)
  await start()
  const hint = async () => {
    const ui = await $.ui.mount(BAND)
    const found = (await ui.find({ type: 'Text', text: /\/rename/ }))?.text
    await ui.unmount()

    return found
  }

  expect(await hint()).toBe('  run /rename <name> to set one')

  await $.command.run({ command: 'rename', args: 'Login screen' })
  expect(await hint()).toBeUndefined()
})

test('the last line waits for agents while subagents run, the main turn done', async ($, on) => {
  const { start } = setup($, on)
  await start()

  const status = async (isWorking: boolean) => {
    const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, isWorking } })
    const found = (await ui.find({ type: 'Text', text: /^[●○◐] / }))?.text
    await ui.unmount()

    return found
  }

  await $.turn.start({ text: 'a', turnId: 't1', agentId: 'a1' })
  await $.turn.start({ text: 'b', turnId: 't2', agentId: 'a2' })
  expect(await status(true)).toBe('● working · 2 agents running')
  expect(await status(false)).toBe('◐ waiting for 2 agents')

  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 't1', agentId: 'a1', reason: 'answer' })
  expect(await status(false)).toBe('◐ waiting for 1 agent')

  await $.turn.complete({ answer: '', durationMs: 1, isAborted: true, turnId: 't2', agentId: 'a2', reason: 'aborted' })
  expect(await status(false)).toBe('○ waiting for input')
})

test('shell lines: yellow while a Bash call runs, magenta in the background until its notice', async ($, on) => {
  const { start, shellLines } = setup($, on)
  const backgroundIds = ['b1', 'b2', 'b3', 'b4']
  let duringCall: string[] = []

  on('tool.call', async (_, e) => {
    if (e.tool === 'TaskStop') {
      return { result: { message: 'stopped' } }
    }

    if (e.tool === 'Bash' && e.run_in_background === true) {
      return { result: { stdout: '', stderr: '', interrupted: false, backgroundTaskId: backgroundIds.shift() } }
    }

    duringCall = await shellLines()

    return { result: { stdout: 'ok', stderr: '', interrupted: false } }
  })
  on('prompt.submit', (_, e) => ({ text: e.text }))
  await start()

  await $.tool.call({ tool: 'Bash', command: 'xcodebuild build', description: 'Build the app', tool_use_id: 't1' })
  expect(duringCall).toEqual(['yellow: ⚙ Build the app'])
  expect(await shellLines()).toEqual([])

  await $.tool.call({ tool: 'Bash', command: 'tail -f build.log', run_in_background: true, tool_use_id: 't2' })
  expect(await shellLines()).toEqual(['magenta: ⚙ tail -f build.log  · background'])

  for (const id of ['t3', 't4', 't5']) {
    await $.tool.call({ tool: 'Bash', command: 'sleep 60', description: `Wait ${id}`, run_in_background: true, tool_use_id: id })
  }

  expect(await shellLines()).toEqual([
    'magenta: ⚙ tail -f build.log  · background',
    'magenta: ⚙ Wait t3  · background',
    'magenta: ⚙ Wait t4  · background',
    'dim:   +1 more',
  ])

  await $.prompt.submit({
    text: '<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>\n'
      + '<task-notification>\n<task-id>b3</task-id>\n<status>failed</status>\n</task-notification>',
  })
  expect(await shellLines()).toEqual(['magenta: ⚙ Wait t3  · background', 'magenta: ⚙ Wait t5  · background'])

  await $.tool.call({ tool: 'TaskStop', task_id: 'b4' })
  expect(await shellLines()).toEqual(['magenta: ⚙ Wait t3  · background'])
})

test('a Bash call running now shows ahead of the background shells', async ($, on) => {
  const { start, shellLines } = setup($, on)
  const backgroundIds = ['b1', 'b2', 'b3']
  let duringCall: string[] = []

  on('tool.call', async (_, e) => {
    if (e.tool === 'Bash' && e.run_in_background === true) {
      return { result: { stdout: '', stderr: '', interrupted: false, backgroundTaskId: backgroundIds.shift() } }
    }

    duringCall = await shellLines()

    return { result: { stdout: 'ok', stderr: '', interrupted: false } }
  })
  await start()

  for (const id of ['t1', 't2', 't3']) {
    await $.tool.call({ tool: 'Bash', command: 'sleep 60', description: `Wait ${id}`, run_in_background: true, tool_use_id: id })
  }

  await $.tool.call({ tool: 'Bash', command: 'xcodebuild build', description: 'Build the app', tool_use_id: 't4' })
  expect(duringCall).toEqual([
    'yellow: ⚙ Build the app',
    'magenta: ⚙ Wait t1  · background',
    'magenta: ⚙ Wait t2  · background',
    'dim:   +1 more',
  ])
})

test("a subagent's shells go when its turn ends: the engine stops them with no notice", async ($, on) => {
  const { start, shellLines } = setup($, on)
  const backgroundIds = ['b1', 'b2', 'b3']

  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false, backgroundTaskId: backgroundIds.shift() } }))
  await start()

  const background = (description: string, agentId?: string) =>
    $.tool.call({ tool: 'Bash', command: 'sleep 60', description, run_in_background: true, ...(agentId ? { agentId } : {}) })
  const complete = (agentId?: string) =>
    $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer', ...(agentId ? { agentId } : {}) })

  await background('Main loop')
  await background('Agent one', 'a1')
  await background('Agent two', 'a2')
  await complete('a1')
  expect(await shellLines()).toEqual(['magenta: ⚙ Main loop  · background', 'magenta: ⚙ Agent two  · background'])

  // The main loop's background shells outlive its turn.
  await complete()
  expect(await shellLines()).toEqual(['magenta: ⚙ Main loop  · background', 'magenta: ⚙ Agent two  · background'])
})

test('shells an earlier version stored, without their agent, are dropped', async ($, on) => {
  const { start, shellLines } = setup($, on)
  on('state.get', { plugin: 'header-title', key: 'shells' }, () => ({
    value: { value: [{ id: 't1', taskId: 'b1', label: 'Find turn.step dispatch sites' }], version: 1 },
  }))
  await start()

  expect(await shellLines()).toEqual([])
})
