# The `claude-kit` Marketplace

This repository is a marketplace of plugins for Claude Code. The plugins add skills, mods, and dashboards to Claude Code.

## Plugins

| Plugin | Type | Function |
|---|---|---|
| [`header-title`](plugins/header-title) | Mod | Shows a band above the prompt. The band shows the name of the session, the folder, the limits, and the status. |
| [`writing-ste`](plugins/writing-ste) | Skill | Writes texts in ASD-STE100 Simplified Technical English (STE). It also does the STE check of a text. |

The `README.md` file of each plugin gives the full procedure to install it and to use it.

## Install a Plugin

1. Start a Claude Code session in the terminal:

   ```bash
   claude
   ```

2. Type this command in the session:

   ```text
   /plugin install header-title --marketplace rexcosta/claude-kit
   ```

   NOTE: For a different plugin, replace `header-title` with the name of that plugin.

3. When Claude Code shows `Add marketplace?`, type `y`.
4. Select `user` with the `Enter` key.

   NOTE: With `user`, Claude Code loads the plugin in all your sessions.

## Get New Versions

1. Get the new version of the marketplace:

   ```bash
   claude plugin marketplace update claude-kit
   ```

2. Get the new version of each plugin. For example:

   ```bash
   claude plugin update header-title@claude-kit
   ```

3. Type `/reload-plugins` in each session that is open.

## Add a Plugin to the Marketplace

1. Put the plugin in a new folder in the `plugins` folder.
2. Put a copy of the `LICENSE` file in the folder of the plugin.
3. Add an entry for the plugin to the `plugins` list in `.claude-plugin/marketplace.json`.
4. Do a check of the marketplace:

   ```bash
   claude plugin validate .
   ```

## Conditions to Use the Code

The `LICENSE` file gives the conditions to use the code. These are the conditions of the `MIT License`.

Each plugin folder has a copy of the `LICENSE` file. Claude Code installs only the folder of the plugin, and the copy goes with it.
