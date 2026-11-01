# Header Title Mod for Claude Code

The `header-title` mod shows a band above the prompt of Claude Code. The band shows these items:

- The name of the session.
- The folder, and the git branch or the worktree.
- The part of the context window that the session uses, the model, and the effort level.
- The 5-hour limit and the 7-day limit.
- The status of the turn and of the subagents.
- The `Bash` commands that did not complete.

## Before You Start

The Mac must have these items:

- Claude Code 2.1.314 or a higher version. The mod uses the API of this version.
- `git` and `grep`. The mod uses `git` to find the branch. The mod uses `grep` to find the name of the session.

## Install the Mod

1. If you put the mod in the `~/.claude/mods/header-title` folder before, remove that copy of the mod. Refer to [Remove the Copy in the Mods Folder](#remove-the-copy-in-the-mods-folder).

   NOTE: Claude Code loads each copy of the mod. If you do not remove the copy in this folder, Claude Code loads two copies.

2. Start a Claude Code session in the terminal:

   ```bash
   claude
   ```

3. Type this command in the session:

   ```text
   /plugin install header-title --marketplace rexcosta/claude-kit
   ```

4. When Claude Code shows `Add marketplace?`, type `y`.

   NOTE: Claude Code adds the `claude-kit` marketplace one time. Then you can install the other plugins of the marketplace with a shorter command.

5. Select `user` with the `Enter` key.

   NOTE: With `user`, Claude Code loads the mod in all your sessions. The desktop app also loads the mod.

6. Make sure that Claude Code shows `Installed header-title. Plugin is now active.`

   NOTE: The band shows above the prompt immediately.

To install the mod without a session, use this command:

```bash
claude plugin install header-title --marketplace rexcosta/claude-kit
```

To install the mod in the desktop app, do these steps:

1. Select the `+` button near the prompt.
2. Select `Plugins`.
3. Select `Add marketplace`.
4. Type `rexcosta/claude-kit`.
5. Select `Add plugin`.

## Use the Mod

- To give a name to the session, use `/rename`. If the session has no name, the band shows "Unnamed session".
- If the terminal does not have sufficient rows for the band, the band shows the two limits on one row.

## Get a New Version of the Mod

1. Get the new version of the marketplace:

   ```bash
   claude plugin marketplace update claude-kit
   ```

2. Get the new version of the mod:

   ```bash
   claude plugin update header-title@claude-kit
   ```

3. Type `/reload-plugins` in each session that is open.

   NOTE: You can also start a new session. A new session loads the new version.

## Remove the Mod

1. Remove the mod:

   ```bash
   claude plugin uninstall header-title@claude-kit
   ```

2. Start a new session.

## Remove the Copy in the Mods Folder

A copy of the mod can be in the `~/.claude/mods/header-title` folder. The `CLAUDE_CODE_PLUGIN_DIRS` environment variable in `~/.claude/settings.json` then tells Claude Code to load the mod from this folder.

1. In the `env` object of `~/.claude/settings.json`, remove `~/.claude/mods/header-title` from `CLAUDE_CODE_PLUGIN_DIRS`.
2. If `CLAUDE_CODE_PLUGIN_DIRS` has no other folder, remove the environment variable.
3. Start a new session.

## Change the Mod

1. Download the repository:

   ```bash
   git clone https://github.com/rexcosta/claude-kit.git
   cd claude-kit
   ```

2. Make the changes in the `plugins/header-title` folder.
3. Do a check of the mod:

   ```bash
   claude plugin validate plugins/header-title
   ```

4. Do the tests of the mod:

   ```bash
   claude plugin test plugins/header-title
   ```

   NOTE: The output must show `0 fail`.

5. Increase the `version` in `plugins/header-title/.claude-plugin/plugin.json`.

   NOTE: The version tells `claude plugin update` that the mod has changes.

6. Send the changes to GitHub in a new branch:

   ```bash
   git switch -c BRANCH-NAME
   git add plugins/header-title
   git commit -m "header-title: DESCRIPTION OF THE CHANGE"
   git push -u origin BRANCH-NAME
   ```

   NOTE: The `main` branch accepts changes only from a PR.

7. Make a PR for the branch:

   ```bash
   gh pr create --fill
   ```

8. If the `main` branch has new commits, put your branch on top of `main`:

   ```bash
   git fetch origin
   git rebase origin/main
   git push --force-with-lease
   ```

   NOTE: You can also select `Update branch` and then `Update with rebase` on the page of the PR.

9. After the approval of the PR, merge the PR with a merge commit:

   ```bash
   gh pr merge --merge
   ```

   NOTE: The rules of the repository accept only a merge commit. Then each PR shows as one merge commit in the `main` branch.
