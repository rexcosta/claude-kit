# STE Skill for Claude Code

The `writing-ste` plugin gives the `writing-ste` skill to Claude Code. With this skill, Claude writes texts in ASD-STE100 Simplified Technical English (STE). The skill also has a checker. The checker finds the words and the sentences that do not obey STE.

ASD has the copyright of the ASD-STE100 dictionary. Thus, the plugin does not contain the dictionary. You make the dictionary file on your computer from the ASD-STE100 PDF file.

## Before You Start

The Mac must have these items:

- macOS. The script `build_dictionary.py` uses `PDFKit` of macOS to read the PDF file.
- Python 3.9 or a higher version. The scripts use only the standard library of Python.
- Claude Code 2.1.316 or a higher version. The skill uses the functions of this version.

## Install the Plugin

1. If you have the skill in the `~/.claude/skills/writing-ste` folder, refer to [Move Your Copy of the Skill to the Plugin](#move-your-copy-of-the-skill-to-the-plugin).

   NOTE: Claude Code loads each copy of the skill.

2. Start a Claude Code session in the terminal:

   ```bash
   claude
   ```

3. Type this command in the session:

   ```text
   /plugin install writing-ste --marketplace rexcosta/claude-kit
   ```

4. When Claude Code shows `Add marketplace?`, type `y`.

   NOTE: Claude Code adds the `claude-kit` marketplace one time. Then you can install the other plugins of the marketplace with a shorter command.

5. Select `user` with the `Enter` key.

   NOTE: With `user`, Claude Code loads the skill in all your sessions.

To install the plugin without a session, use this command:

```bash
claude plugin install writing-ste --marketplace rexcosta/claude-kit
```

## Install the Dictionary

1. Get the ASD-STE100 PDF file from `https://www.asd-ste100.org`.
2. In a Claude Code session, type `/writing-ste:writing-ste`.

   NOTE: The skill shows an error. The error gives the command that makes the dictionary file.

3. In the terminal, use the command that the error shows. Replace `PDF` with the path of the PDF file.

   NOTE: Claude can also do the command. Write the path of the PDF file in the session.

4. Type `/writing-ste:writing-ste` again. Make sure that the error does not show.

## Use the Skill

- To make Claude write a text in STE, write "keep ASD-STE100" in your message.
- To do the STE check of a file, write `Do the STE check of FILE` in the session.
- To find if a word is approved, and its alternatives, write `Is WORD an approved STE word?` in the session.

## Add a Word

Claude adds the technical nouns and the technical verbs to the word list of the user. This list is `~/.claude/plugins/data/writing-ste-claude-kit/ste-word-list.md`. All your projects use this list.

To add a word, write `Add WORD to my STE word list` in the session.

## Get a New Version of the Plugin

1. Get the new version of the marketplace:

   ```bash
   claude plugin marketplace update claude-kit
   ```

2. Get the new version of the plugin:

   ```bash
   claude plugin update writing-ste@claude-kit
   ```

3. Type `/reload-plugins` in each session that is open.

   NOTE: The new version does not change the dictionary file or the word list of the user.

## Make the Dictionary File Again

When ASD publishes a new issue of ASD-STE100, do these steps:

1. Get the new PDF file from `https://www.asd-ste100.org`.
2. Write `Make the STE dictionary file again from PATH` in a session. Replace `PATH` with the path of the PDF file.

## Move Your Copy of the Skill to the Plugin

Do these steps if you have the skill in the `~/.claude/skills/writing-ste` folder.

1. Put a copy of the dictionary file into the data folder of the plugin:

   ```bash
   mkdir -p ~/.claude/plugins/data/writing-ste-claude-kit
   cp ~/.claude/skills/writing-ste/data/ste100-dictionary.json ~/.claude/plugins/data/writing-ste-claude-kit/
   ```

2. Put your words into `~/.claude/plugins/data/writing-ste-claude-kit/ste-word-list.md`. Your words can be in these files:

   - `~/.claude/skills/writing-ste/data/ste-word-list.md`
   - `docs/ste-word-list.md` in each project

   NOTE: Claude can do this step. Write `Move my STE words from FILE to the word list of the user` in a session.

3. In the `CLAUDE.md` file of each project, remove the text about `docs/ste-word-list.md`.

   NOTE: The plugin does not read the word list of a project.

4. Remove your copy of the skill.

   CAUTION: Do steps 1 and 2 first. This command also removes the dictionary file and the word list in that folder.

   ```bash
   rm -r ~/.claude/skills/writing-ste
   ```

5. Start a new session.

   NOTE: If your copy of the skill stays, Claude loads two `writing-ste` skills.

## Add the STE Rules to `CLAUDE.md`

This step is optional. With these rules, Claude uses the skill when you write "keep ASD-STE100". The second rule tells Claude to use the skill for each build prompt, specification, `CLAUDE.md` file, and skill file. The other rules tell Claude how to write a procedure.

CAUTION: Use `>>`, not `>`. If you use `>`, the command removes all the text that is in the file.

```bash
cat >> ~/.claude/CLAUDE.md <<'EOF'

# Simplified Technical English

- If the user wants a text in STE or in ASD-STE100, use the `writing-ste` skill. An example is "keep ASD-STE100".
- Use the `writing-ste` skill when you write or change a build prompt, a specification, a `CLAUDE.md` file, or a skill file.
- Write a procedure as a list of steps. Give a number to each step. Start each step with a verb.
- Put a CAUTION before the command that it is for.
- Put a NOTE after the command. The NOTE gives the cause of the command.
- To refer to a different text, write "refer to". Do not write "see".
- Give terminal commands, not steps in `Finder`.
- Use US English.
EOF
```

## Remove the Plugin

1. Remove the plugin:

   CAUTION: This command also removes the data folder of the plugin. The data folder contains the dictionary file and the word list of the user. To keep the data folder, add `--keep-data` to the command.

   ```bash
   claude plugin uninstall writing-ste@claude-kit
   ```

2. Start a new session.

## The Copyright of the Dictionary

- ASD has the copyright of the ASD-STE100 dictionary. Do not publish the dictionary file or parts of it.
- The dictionary file is `~/.claude/plugins/data/writing-ste-claude-kit/ste100-dictionary.json`. The repository does not contain this file.
- The tests use words that are not from the dictionary.

## Change the Plugin

1. Download the repository:

   ```bash
   git clone https://github.com/rexcosta/claude-kit.git
   cd claude-kit
   ```

2. Make the changes in the `plugins/writing-ste` folder.
3. Do the tests of the scripts:

   ```bash
   python3 -m unittest discover -s plugins/writing-ste/skills/writing-ste/scripts
   ```

   NOTE: The last line of the output must be `OK`. The tests in `RealDictionaryTest` use the dictionary file in the data folder. These tests make sure that the general word list has no errors. They also make sure that no text in the test files is a meaning, a note, or an alternative of the dictionary. They cannot find the examples of the dictionary. Do not put text from the dictionary into a test.

4. Do a check of the plugin:

   ```bash
   claude plugin validate plugins/writing-ste
   ```

5. Increase the `version` in `plugins/writing-ste/.claude-plugin/plugin.json`.

   NOTE: The version tells `claude plugin update` that the plugin has changes.

6. Send the changes to GitHub in a new branch:

   ```bash
   git switch -c BRANCH-NAME
   git add plugins/writing-ste
   git commit -m "writing-ste: DESCRIPTION OF THE CHANGE"
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
