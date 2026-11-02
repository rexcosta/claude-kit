---
name: writing-ste
description: Use when you write or change a text that must obey ASD-STE100 Simplified Technical English (STE), or when the instructions of a project tell you to use STE or the writing-ste skill.
allowed-tools:
  - Bash(python3 -I "${CLAUDE_SKILL_DIR}/scripts/ste_check.py" *)
---

# STE Texts

## Status of the Dictionary

!`python3 -I "${CLAUDE_SKILL_DIR}/scripts/ste_check.py" --status --data "${CLAUDE_PLUGIN_DATA}"`

Examine the status above before you do the procedure:

- If the status starts with `OK`, do the procedure.
- If the status is `[shell command execution disabled by policy]`, get the status with this command: `python3 -I "${CLAUDE_SKILL_DIR}/scripts/ste_check.py" --status --data "${CLAUDE_PLUGIN_DATA}"`
- If the status starts with `ERROR`, do these steps:
  1. If the user gave you the path of the ASD-STE100 PDF file, make the dictionary file. Use the command in the section "Data". Then get the status again.
  2. If the status starts with `ERROR` again, show the full status text to the user. Do not write or change an STE text. Stop.

## About STE

ASD-STE100 Simplified Technical English (STE) has rules and a dictionary of approved words. The checker `scripts/ste_check.py` finds many errors, but not all of them. You must also examine the meaning of each word and the structure of each sentence.

## Procedure

1. Write the text in Markdown. Obey the rules in the table of this file.
2. Put each text that you must not change between backticks. Examples: commands, file names, code, and messages that are not in STE. The checker does not examine this text.
3. To find if a word is approved, and its alternatives, use this command: `python3 -I "${CLAUDE_SKILL_DIR}/scripts/ste_check.py" --data "${CLAUDE_PLUGIN_DATA}" --lookup WORD`
4. To do the STE check, use this command: `python3 -I "${CLAUDE_SKILL_DIR}/scripts/ste_check.py" --data "${CLAUDE_PLUGIN_DATA}" FILE`
5. Correct each `ERROR`:
   - If a word is not approved, use an alternative that the checker gives. If the meaning changes, write a different sentence (rule 9.1).
   - If a word is a technical noun or a technical verb, add it to the word list of the user. Write its category (rule 1.5 or rule 1.12). Tell the user which words you added.
6. Examine each `REVIEW` item. Make sure that the word has its approved meaning and part of speech.
7. Do the checks in the section "Checks that the Checker Cannot Do".
8. Do steps 4 to 7 again until the checker shows 0 errors. Then show the text or publish it.

## Word Lists

The checker reads two word lists. Each word list gives technical nouns (TN) and technical verbs (TV) for all the projects.

- The general word list is `${CLAUDE_SKILL_DIR}/data/ste-word-list.md`. This list is a part of the plugin. Do not change it.
- The word list of the user is `${CLAUDE_PLUGIN_DATA}/ste-word-list.md`. Add the new words to this list. Obey the instructions at the start of the general word list.

If the word list of the user is not there, make it with this text:

```markdown
# STE Word List of the User

This list gives the technical nouns (TN) and the technical verbs (TV) of the user. The STE checker reads this list and the general word list of the plugin.

| Word | Type | Category | Forms | Information |
|---|---|---|---|---|
```

## Rules

| Rule | Instruction |
|---|---|
| 1.1 to 1.4 | Use only approved words. Use each approved word only with its approved meaning and part of speech. |
| 1.5, 1.12 | You can use the technical nouns and the technical verbs in the word lists. |
| 1.11 | Use the same technical noun for the same item. |
| 2.1 | A multi-word noun can have a maximum of three words. |
| 3.1 to 3.5 | Use only the verb forms that the dictionary gives. Do not use the "-ing" form of a verb. |
| 3.6 | Use the active voice. |
| 4.2 | Write all the words of a sentence. For example, write "do not", not "don't". |
| 4.3 | If a sentence has many items, use a vertical list. |
| 4.5 | When possible, put "a", "an", "the", "this", or "these" before a noun. |
| 5.1 | An instruction can have a maximum of 20 words. |
| 5.2, 5.3 | Write one instruction in each sentence. Start the instruction with the verb. |
| 5.4 | Put a condition before the instruction. Put "," after the condition. |
| 6.3 | A sentence that gives information can have a maximum of 25 words. |
| 6.5, 6.6 | A paragraph can have only one subject and a maximum of six sentences. |
| 7.1 to 7.3 | Start a "WARNING" or a "CAUTION" with a short instruction. Then give the risk. |
| 8.1 | Do not use ";". |
| GR-6 | Do not use "e.g.", "i.e.", or "etc.". |

## Checks that the Checker Cannot Do

Examine the text for these errors:

- A word with a meaning or a part of speech that is not approved (rules 1.2 and 1.3).
- A multi-word noun of more than three words (rule 2.1).
- An instruction that does not use the active voice (rule 3.6).
- Two instructions in one sentence (rule 5.2).
- A paragraph about more than one subject (rule 6.5).
- Different technical nouns for the same item (rule 1.11).

## Data

- `${CLAUDE_PLUGIN_DATA}/ste100-dictionary.json` contains the words of the ASD-STE100 dictionary. ASD has the copyright. Do not publish this file or parts of it.
- To make the dictionary file, use this command: `python3 -I "${CLAUDE_SKILL_DIR}/scripts/build_dictionary.py" PDF "${CLAUDE_PLUGIN_DATA}/ste100-dictionary.json"`. Replace `PDF` with the path of the ASD-STE100 PDF file.
- When ASD publishes a new issue, make the dictionary file again with the same command.
- To do a test of the scripts, use this command: `python3 -m unittest discover -s "${CLAUDE_SKILL_DIR}/scripts"`
