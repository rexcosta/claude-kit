"""Check a text against ASD-STE100 Simplified Technical English (STE).

Usage:
    python3 ste_check.py [--data FOLDER] [--words FILE] [--dictionary FILE] FILE...
    python3 ste_check.py [--data FOLDER] --lookup WORD...
    python3 ste_check.py [--data FOLDER] --status

The data folder of the plugin (default: $CLAUDE_PLUGIN_DATA, or
~/.claude/plugins/data/writing-ste-claude-kit) contains the dictionary file
ste100-dictionary.json. With --status, the checker does only the dictionary
check: the output starts with OK or ERROR, and the exit code is always 0.

The checker reads Markdown or plain text. It does not check front matter, code
blocks, inline code, URLs, or text in quotation marks (rule 8.6: quoted text
counts as one word). The checker reads two word lists of technical nouns (TN)
and technical verbs (TV): the general word list of the plugin
(data/ste-word-list.md) and the word list of the user (ste-word-list.md in the
data folder). All projects use the same two word lists. The checker gives findings
only for the word list of the user: the tests of the plugin examine the general list.

Each finding is an ERROR (the text does not obey a rule) or a REVIEW item (a
person must examine the word: its part of speech or its meaning). The exit code
is 1 if there are errors, 0 if there are none, and 2 for a usage error.
"""
import argparse
import json
import os
import re
import sys
from collections import namedtuple
from html import unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ID = "writing-ste-claude-kit"
DICTIONARY_FILE = "ste100-dictionary.json"
WORDS_FILE = "ste-word-list.md"
GENERAL_WORDS = HERE.parent / "data" / WORDS_FILE
ASD_URL = "https://www.asd-ste100.org"

INSTRUCTION_LIMIT = 20  # rule 5.1
DESCRIPTION_LIMIT = 25  # rule 6.3
PARAGRAPH_LIMIT = 6     # rule 6.6
TN_CATEGORIES = {str(n) for n in range(1, 23)}                  # rule 1.5
TV_CATEGORY_RE = re.compile(r"^(1[a-f]?|2[a-c]?|3[a-f]?|4)$")  # rule 1.12
# The type of a technical word: (part of speech, name, rule).
TECHNICAL = {"TN": ("n", "noun", "1.5"), "TV": ("v", "verb", "1.12")}

Finding = namedtuple("Finding", "level rule line message")

OPAQUE = ""  # code, a URL, or quoted text: one word that is not checked
PAREN = ""   # text in parentheses: one word in its sentence (rule 8.5)

# A word starts with a letter. Digits before or after the letter make one identifier
# ("2FA", "STE100"). In "20-minute", the word is "minute".
WORD_RE = re.compile(r"[0-9]*[A-Za-z][A-Za-z0-9'’]*(?:-[A-Za-z0-9][A-Za-z0-9'’]*)*")
TOKEN_RE = re.compile(OPAQUE + "|" + PAREN
                      + r"|[A-Za-z0-9][A-Za-z0-9'’]*(?:[-.,:/][A-Za-z0-9][A-Za-z0-9'’]*)*%?")
CONTRACTION_RE = re.compile(
    r"\b[A-Za-z]+n['’]t\b|\b[A-Za-z]+['’](?:re|ve|ll|d|m)\b"
    r"|\b(?:it|that|there|here|what|who|let|he|she|where|how)['’]s\b", re.I)
LATIN_RE = re.compile(r"\b(?:e\.\s?g|i\.\s?e|etc|viz|cf)\b\.?", re.I)
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[\"“(\[]?[A-Z0-9" + OPAQUE + r"])")
UNITS = {"mm", "cm", "m", "km", "in", "ft", "kg", "g", "mg", "lb", "l", "ml", "s",
         "ms", "min", "h", "kb", "mb", "gb", "tb", "hz", "khz", "mhz", "ghz", "v",
         "a", "w", "kw", "psi", "kpa", "bar", "ohms", "%"}
# Words that can start a condition before an instruction: "If ..., do ...".
CONDITIONS = {"if", "when", "before", "after", "while", "until", "unless", "to",
              "for", "during", "in", "on", "at", "with", "without", "from", "as",
              "where", "because", "then"}

HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*$")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")
CODE_RE = re.compile(r"(`+)(.+?)\1")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL_RE = re.compile(r"<?https?://[^\s>)]+>?")
TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
QUOTE_RE = re.compile(r"\"[^\"]*\"|“[^”]*”")
EMPHASIS_RE = re.compile(r"\*\*|__|(?<![A-Za-z0-9])[*_]|[*_](?![A-Za-z0-9])")


def plural_forms(word):
    head, _, last = word.rpartition(" ")
    prefix = head + " " if head else ""
    if re.search(r"(s|x|z|ch|sh)$", last):
        return [prefix + last + "es"]
    if re.search(r"[^aeiou]y$", last):
        return [prefix + last[:-1] + "ies"]
    return [prefix + last + "s"]


def regular_verb_forms(word):
    """Return the third person and past forms of a regular verb.

    A doubled final consonant ("committed") is added as a second spelling,
    because the stress of the word decides it ("edited").
    """
    first, sep, tail = word.partition(" ")
    if re.search(r"(s|x|z|ch|sh)$", first):
        forms = [first + "es", first + "ed"]
    elif re.search(r"[^aeiou]y$", first):
        forms = [first[:-1] + "ies", first[:-1] + "ied"]
    elif first.endswith("e"):
        forms = [first + "s", first + "d"]
    else:
        forms = [first + "s", first + "ed"]
        if re.search(r"[^aeiou][aeiou][^aeiouwxy]$", first):
            forms.append(first + first[-1] + "ed")
    return [f + sep + tail for f in forms]


def add_form(form, single, phrases, value):
    """Add a form to single, and a form with more than one word also to phrases.

    A token of a text has no spaces, so only --lookup finds a phrase in single.
    """
    parts = form.split()
    single.setdefault(" ".join(parts), []).append(value)
    if len(parts) > 1 and all(WORD_RE.fullmatch(p) for p in parts):
        phrases.setdefault(parts[0], []).append(tuple(parts))


def phrase_length(phrases, keys, i):
    best = 0
    for phrase in phrases.get(keys[i], ()):
        if len(phrase) > best and tuple(keys[i:i + len(phrase)]) == phrase:
            best = len(phrase)
    return best


class Dictionary:
    """The words of the ASD-STE100 dictionary, from build_dictionary.py."""

    def __init__(self, data):
        self.source = data.get("source") or "ASD-STE100"
        self.approved, self.phrases, self.not_approved, self.verbs = {}, {}, {}, set()
        for e in data["approved"]:
            forms = [e["word"]] + list(e.get("forms") or [])
            if e["pos"] == "v" and not e.get("forms"):
                forms += regular_verb_forms(e["word"])
            if e["pos"] == "n":
                forms += plural_forms(e["word"])
            for form in forms:
                add_form(form, self.approved, self.phrases, e)
            if e["pos"] == "v":
                self.verbs.add(e["word"].split()[0])
        for e in data["not_approved"]:
            self.not_approved.setdefault(e["word"], []).append(e)

    def is_approved(self, word):
        return word in self.approved

    def reviews(self, word):
        """Return the REVIEW findings for an approved word, as (rule, message)."""
        entries = list({id(e): e for e in self.approved[word]}.values())
        found = []
        other_pos = [n for n in self.not_approved.get(word, [])
                     if n["pos"] not in {e["pos"] for e in entries}]
        if other_pos:
            message = '"%s" is approved only as %s.' % (word, ", ".join(
                "%s (%s)" % (e["word"].upper(), e["pos"]) for e in entries))
            for n in other_pos:
                message += " As %s (%s), %s" % (word, n["pos"], replacement(n))
            found.append(("1.2", message))
        for e in entries:
            if e.get("restricted"):
                found.append(("1.3", '"%s" (%s) is approved only with the meaning "%s".'
                              ' For other meanings, use: %s.' % (
                                  word, e["pos"], e["meaning"],
                                  ", ".join(e["other_meanings"]) or "see dictionary page " + e["page"])))
            if e.get("note"):
                found.append(("1.3", '"%s" (%s): %s' % (word, e["pos"], e["note"])))
        return found

    def not_approved_message(self, word):
        return '"%s" is not approved. %s' % (word, " ".join(
            "As %s (%s), %s" % (word, n["pos"], replacement(n))
            for n in self.not_approved[word]))


def replacement(entry):
    """Tell how to replace a word that is not approved."""
    if entry["alternatives"]:
        text = "use: %s." % ", ".join(entry["alternatives"])
    elif entry.get("note"):
        text = entry["note"]
    else:
        text = "use a different word or construction."
    return "%s See dictionary page %s." % (text, entry["page"])


def default_data_folder():
    """Return the data folder of the plugin, which stays after each update."""
    if os.environ.get("CLAUDE_PLUGIN_DATA"):
        return Path(os.environ["CLAUDE_PLUGIN_DATA"])
    return Path.home() / ".claude" / "plugins" / "data" / PLUGIN_ID


class DictionaryError(Exception):
    """The dictionary file is missing or not correct. The text tells how to make it."""


def dictionary_error(path, missing):
    if missing:
        first = "ERROR: The ASD-STE100 dictionary is not installed."
    else:
        first = ("ERROR: The dictionary file is not correct: %s\n\n"
                 "Make the dictionary file again." % path)
    return "\n".join([
        first,
        "",
        "1. Get the ASD-STE100 PDF file from %s." % ASD_URL,
        "2. On a Mac, use this command:",
        '   python3 -I "%s" PDF "%s"' % (HERE / "build_dictionary.py", path),
        "   NOTE: Replace PDF with the path of the PDF file.",
        "3. Use the skill again.",
    ])


def load_dictionary(path):
    """Return the dictionary in the file. Raise DictionaryError if it is missing or not correct.

    The dictionary check must never stop with a Python error, because Claude Code then
    drops the skill. Thus each error of the file or of its folder is a DictionaryError.
    """
    try:
        if not path.exists():
            error = dictionary_error(path, missing=True)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            dictionary = Dictionary(data)
            if data["approved"] and data["not_approved"]:
                return dictionary
            error = dictionary_error(path, missing=False)
    except Exception:
        error = dictionary_error(path, missing=False)
    raise DictionaryError(error)


def status(data):
    try:
        dictionary = load_dictionary(data / DICTIONARY_FILE)
    except DictionaryError as e:
        return str(e)
    return "OK: The ASD-STE100 dictionary is installed. Source: %s. Data folder: %s" % (
        dictionary.source, data)


class ProjectWords:
    """The technical nouns and verbs of the project, from a Markdown table."""

    def __init__(self, entries):
        self.entries = entries
        self.single, self.phrases, self.verbs = {}, {}, set()
        for e in entries:
            base = e["word"].lower()
            forms = [base] + e["forms"]
            if e["type"] == "TN":
                forms += plural_forms(base)
            elif e["type"] == "TV":
                forms += regular_verb_forms(base)
                self.verbs.add(base.split()[0])
            for form in forms:
                add_form(form, self.single, self.phrases, e)

    @classmethod
    def parse(cls, text):
        entries, columns = [], None
        for number, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s.startswith("|"):
                columns = None
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if columns is None:
                names = [c.lower() for c in cells]
                if "word" in names and "type" in names:
                    columns = {name: k for k, name in enumerate(names)}
                continue
            if all(SEPARATOR_CELL_RE.match(c) for c in cells if c):
                continue

            def cell(name):
                k = columns.get(name)
                return cells[k] if k is not None and k < len(cells) else ""

            word = cell("word").strip("`* ")
            if word:
                entries.append({
                    "word": word, "type": cell("type").upper(), "category": cell("category"),
                    "forms": [f.strip().lower() for f in cell("forms").split(",") if f.strip()],
                    "line": number})
        return cls(entries)

    def knows(self, word):
        return word in self.single

    def reviews(self, word, dictionary):
        """Return the REVIEW findings for a word of the lists, as (rule, message).

        The dictionary can give a technical word as not approved with the same part
        of speech. Then the word must have only its technical meaning.
        """
        found = []
        for base, kind in sorted({(e["word"].lower(), e["type"]) for e in self.single[word]}):
            if kind not in TECHNICAL:
                continue
            pos, name, rule = TECHNICAL[kind]
            listed = [n for n in dictionary.not_approved.get(base, []) if n["pos"] == pos]
            if listed:
                found.append((rule, '"%s" is a technical %s in a word list. Use it only with'
                              ' its technical meaning. %s' % (word, name, " ".join(
                                  "As %s (%s) with a different meaning, %s" % (
                                      base, pos, replacement(n)) for n in listed))))
        return found

    def validate(self, dictionary):
        findings = []
        for e in self.entries:
            word, kind, line = e["word"].lower(), e["type"], e["line"]
            category = re.sub(r"[\s).]", "", e["category"]).lower()
            if kind not in ("TN", "TV"):
                findings.append(Finding("ERROR", "1.5", line, '"%s": the type must be TN'
                                        ' (technical noun) or TV (technical verb).' % e["word"]))
                continue
            noun = kind == "TN"
            rule, pos, name = ("1.5", "n", "noun") if noun else ("1.12", "v", "verb")
            if noun and category not in TN_CATEGORIES:
                findings.append(Finding("ERROR", rule, line, '"%s": the category must be a'
                                        ' technical noun category, 1 to 22.' % e["word"]))
            if not noun and not TV_CATEGORY_RE.match(category):
                findings.append(Finding("ERROR", rule, line, '"%s": the category must be a'
                                        ' technical verb category: 1a to 1f, 2a to 2c,'
                                        ' 3a to 3f, or 4.' % e["word"]))
            if any(a["word"] == word and a["pos"] == pos
                   for a in dictionary.approved.get(word, [])):
                findings.append(Finding("ERROR", rule, line, '"%s" is an approved %s in the'
                                        ' dictionary. Remove it from this list.' % (word, name)))
                continue
            listed = dictionary.not_approved.get(word, [])
            if listed and all(n["pos"] != pos for n in listed):
                findings.append(Finding("REVIEW", rule, line, '"%s": the dictionary gives this'
                                        ' word only as %s. A technical %s must be a %s. Use it'
                                        ' only as a %s.' % (
                                            word, ", ".join("(%s)" % n["pos"] for n in listed),
                                            name, name, name)))
        return findings


class Block:
    """A heading, paragraph, list item, or table cell with its source lines."""

    def __init__(self, kind, lines):
        self.kind = kind
        self.lines = lines


def markdown_blocks(text):
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                start = j + 1
                break
    blocks, current, last_row = [], None, []
    fence = ""  # the characters that opened the code block, while the checker is in it
    comment = False
    for index in range(start, len(lines)):
        number, raw = index + 1, lines[index]
        s = raw.strip()
        if fence:
            # Only the same character, at least as many times, closes it (CommonMark).
            m = FENCE_RE.match(raw)
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence)
                    and not m.group(2).strip()):
                fence = ""
            continue
        if comment:
            comment = "-->" not in s
            continue
        m = FENCE_RE.match(raw)
        if m:
            fence, current = m.group(1), None
            continue
        if s.startswith("<!--"):
            comment, current = "-->" not in s, None
            continue
        if not s:
            current = None
            continue
        heading = HEADING_RE.match(s)
        if heading:
            blocks.append(Block("heading", [(number, heading.group(1))]))
            current = None
            continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if any(cells) and all(SEPARATOR_CELL_RE.match(c) for c in cells if c):
                for block in last_row:
                    block.kind = "header"
            else:
                last_row = [Block("cell", [(number, c)]) for c in cells if c]
                blocks += last_row
            current = None
            continue
        if s.startswith(">"):
            s = s.lstrip(">").strip()
            if not s:
                current = None
                continue
        item = ITEM_RE.match(s)
        if item:
            current = Block("item", [(number, item.group(1))])
            blocks.append(current)
        elif current is None:
            current = Block("paragraph", [(number, s)])
            blocks.append(current)
        else:
            current.lines.append((number, s))
    return blocks


def mask(line):
    """Hide the parts of a line that the checker does not check."""
    line = CODE_RE.sub(OPAQUE, line)
    line = IMAGE_RE.sub("", line)
    line = LINK_RE.sub(r"\1", line)
    line = URL_RE.sub(OPAQUE, line)
    line = TAG_RE.sub(" ", line)
    line = unescape(line)
    line = QUOTE_RE.sub(OPAQUE, line)
    line = EMPHASIS_RE.sub("", line)
    return line.replace("\\", "")


def normalize(token):
    word = token.lower().replace("’", "'")
    if word.endswith("'s"):
        word = word[:-2]
    return word.rstrip("'")


# Rule 1.5, category 9: numbers are technical nouns.
NUMBER_WORDS = set(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen"
    " fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty"
    " sixty seventy eighty ninety hundred thousand million".split())
UNKNOWN = "not in the dictionary or the word lists."
UNKNOWN_HELP = ("For a word that is not in the dictionary or the word lists, use an approved"
                " word. If it is a technical noun or verb, add it to the word list of the user"
                " with its category.")


def is_ing_form(word, verbs):
    stem = word[:-3]
    return any(s in verbs for s in (stem, stem + "e", stem[:-1]))


def unknown_parts(word, dictionary, words):
    """Return the parts of a hyphenated word that the checker does not accept."""
    return [p for p in word.split("-") if len(p) > 1 and not words.knows(p)
            and p not in NUMBER_WORDS and not dictionary.is_approved(p)]


def judge(word, dictionary, words, verbs):
    """Return the findings for one word as (level, rule, message).

    verbs: the verbs of the dictionary and of the word lists.
    """
    if words.knows(word):
        return [("REVIEW", rule, message) for rule, message in words.reviews(word, dictionary)]
    if word in NUMBER_WORDS or (dictionary.is_approved(word) and "-" in word):
        return []
    if "-" in word:
        bad = ['"%s"' % p for p in unknown_parts(word, dictionary, words)]
        if not bad:
            return []
        return [("ERROR", "1.1", '"%s": %s %s %s' % (
            word, " and ".join(bad), "is" if len(bad) == 1 else "are", UNKNOWN))]
    if dictionary.is_approved(word):
        return [("REVIEW", rule, message) for rule, message in dictionary.reviews(word)]
    if word in dictionary.not_approved:
        return [("ERROR", "1.1", dictionary.not_approved_message(word))]
    if word.endswith("ing") and is_ing_form(word, verbs):
        return [("ERROR", "3.5", '"%s": do not use the -ing form of a verb. Use a different'
                 ' construction.' % word)]
    return [("ERROR", "1.1", '"%s" is %s' % (word, UNKNOWN))]


def lookup(word, dictionary, words):
    """Return one line that tells the status of a word or a phrase."""
    key = " ".join(normalize(word).split())
    return "%s: %s" % (key, describe(key, dictionary, words))


def describe(key, dictionary, words):
    """Tell the status of a word, as the checker examines it."""
    parts = []
    if words.knows(key):
        # A word can have more than one row, one for each meaning.
        rows = {(e["word"], e["type"], e["category"]): None for e in words.single[key]}
        parts += ["%s (%s, category %s) is in a word list." % row for row in rows]
    if dictionary.is_approved(key):
        for e in {id(e): e for e in dictionary.approved[key]}.values():
            text = "%s (%s) is approved: %s." % (e["word"].upper(), e["pos"], e["meaning"])
            if e.get("forms"):
                text += " Forms: %s." % ", ".join(e["forms"])
            if e.get("restricted"):
                text += " For other meanings, use: %s." % ", ".join(e["other_meanings"])
            if e.get("note"):
                text += " " + e["note"]
            parts.append(text)
    if key in dictionary.not_approved:
        parts.append(dictionary.not_approved_message(key))
    if key in NUMBER_WORDS:
        parts.append('"%s" is a number: a technical noun of category 9 (rule 1.5).' % key)
    if parts:
        return " ".join(parts)
    if "-" in key:
        # The checker accepts a hyphenated word if it accepts each part.
        if unknown_parts(key, dictionary, words):
            first = '"%s" is %s' % (key, UNKNOWN)
        else:
            first = 'The checker accepts "%s", because it accepts each part.' % key
        return " ".join([first] + ["%s: %s" % (p, describe(p, dictionary, words))
                                   for p in key.split("-") if len(p) > 1])
    return '"%s" is %s' % (key, UNKNOWN)


def check_words(tokens, dictionary, words, verbs, hits, judged):
    """Check the words of a block. Each token is (word, line number).

    A phrase can continue on the next line of the block. judged keeps the findings
    of each word, because a text can use a word many times.
    """
    keys = [normalize(t) for t, _ in tokens]
    i = 0
    while i < len(tokens):
        n = phrase_length(words.phrases, keys, i) or phrase_length(dictionary.phrases, keys, i)
        if n:
            i += n
            continue
        (token, number), key = tokens[i], keys[i]
        i += 1
        # Rule 8.6: an alphanumeric identifier such as ASD-STE100 is one word.
        if CONTRACTION_RE.fullmatch(token) or len(key) < 2 or any(c.isdigit() for c in key):
            continue
        if key not in judged:
            judged[key] = judge(key, dictionary, words, verbs)
        for level, rule, message in judged[key]:
            hit = hits.setdefault((level, rule, key), [message, []])
            if number not in hit[1]:
                hit[1].append(number)


def without_parentheses(sentence):
    """Return the sentence with each text in parentheses as one word, and those texts."""
    outer, inner, buf, depth = "", [], "", 0
    for ch in sentence:
        if ch == "(":
            if depth:
                buf += ch
            else:
                buf = ""
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth:
                buf += ch
            else:
                inner.append(buf)
                outer += " " + PAREN + " "
        elif depth:
            buf += ch
        else:
            outer += ch
    if depth:
        outer += "(" + buf
    return outer, inner


def count_words(text):
    tokens = TOKEN_RE.findall(text)
    count, unit = 0, False
    for i, t in enumerate(tokens):
        if unit:
            unit = False
            continue
        count += 1
        unit = t[0].isdigit() and i + 1 < len(tokens) and tokens[i + 1].lower() in UNITS
    return count


def is_instruction(sentence, verbs):
    first = TOKEN_RE.search(sentence)
    if not first or first.group() in (OPAQUE, PAREN) or first.group()[0].isdigit():
        return False
    words = [w.lower() for w in WORD_RE.findall(sentence)]
    if words[0] in verbs:
        return True
    if words[0] in CONDITIONS and "," in sentence:
        after = WORD_RE.findall(sentence.split(",", 1)[1])
        return bool(after) and after[0].lower() in verbs
    return False


def check_length(sentence, line, verbs, findings):
    count = count_words(sentence)
    if is_instruction(sentence, verbs):
        limit, rule, name = INSTRUCTION_LIMIT, "5.1", "instruction"
    else:
        limit, rule, name = DESCRIPTION_LIMIT, "6.3", "description"
    if count > limit:
        preview = " ".join(sentence.replace(OPAQUE, "`…`").replace(PAREN, "(…)").split())
        findings.append(Finding("ERROR", rule, line, 'This %s has %d words. The limit is %d.'
                                ' "%s"' % (name, count, limit, preview[:70])))


def check_text(text, dictionary, words):
    findings, hits, judged = [], {}, {}
    verbs = dictionary.verbs | words.verbs
    for block in markdown_blocks(text):
        joined, starts, tokens = "", [], []
        for number, raw in block.lines:
            masked = mask(raw)
            for _ in re.finditer(";", masked):
                findings.append(Finding("ERROR", "8.1", number, "Do not use a semicolon."
                                        " Write two sentences."))
            for m in CONTRACTION_RE.finditer(masked):
                findings.append(Finding("ERROR", "4.2", number,
                                        'Do not use contractions: "%s".' % m.group()))
            for m in LATIN_RE.finditer(masked):
                findings.append(Finding("ERROR", "GR-6", number, 'Do not use the Latin'
                                        ' abbreviation "%s". Write "for example" or'
                                        ' "that is", or omit it.' % m.group()))
            tokens += [(t, number) for t in WORD_RE.findall(masked)]
            starts.append((len(joined), number))
            joined += masked + " "
        check_words(tokens, dictionary, words, verbs, hits, judged)
        if block.kind in ("heading", "header"):
            continue
        count, position = 0, 0
        for sentence in (s.strip() for s in SENTENCE_END_RE.split(joined)):
            if not sentence:
                continue
            offset = joined.find(sentence, position)
            position = offset + len(sentence)
            line = max(n for start, n in starts if start <= max(offset, 0))
            outer, inner = without_parentheses(sentence)
            for part in [outer] + inner:
                check_length(part, line, verbs, findings)
            count += 1
        if block.kind == "paragraph" and count > PARAGRAPH_LIMIT:
            findings.append(Finding("ERROR", "6.6", block.lines[0][0], "This paragraph has %d"
                                    " sentences. The limit is %d." % (count, PARAGRAPH_LIMIT)))
    for (level, rule, _), (message, numbers) in hits.items():
        if len(numbers) > 1:
            message += " (lines %s)" % ", ".join(map(str, numbers))
        findings.append(Finding(level, rule, numbers[0], message))
    return sorted(findings, key=lambda f: (f.line or 0, f.level, f.rule))


class ReadError(Exception):
    """The checker cannot read a file. The text tells why."""


def read_file(path):
    """Return the text of a file. Raise ReadError if the checker cannot read it."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        reason = e.strerror if isinstance(e, OSError) else "the file is not UTF-8 text"
        raise ReadError("The checker cannot read %s: %s." % (path, reason)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a text against ASD-STE100.")
    parser.add_argument("files", nargs="*", help="Markdown or text files")
    parser.add_argument("--data", default="", metavar="FOLDER",
                        help="data folder of the plugin (default: %s)" % default_data_folder())
    parser.add_argument("--status", action="store_true",
                        help="do only the dictionary check; the exit code is always 0")
    parser.add_argument("--dictionary", metavar="FILE",
                        help="dictionary file (default: FOLDER/%s)" % DICTIONARY_FILE)
    parser.add_argument("--general-words", metavar="FILE",
                        help="general word list (default: %s)" % GENERAL_WORDS)
    parser.add_argument("--words", metavar="FILE",
                        help="word list of the user (default: FOLDER/%s)" % WORDS_FILE)
    parser.add_argument("--lookup", nargs="+", metavar="WORD",
                        help="show the status, meaning, and alternatives of words")
    args = parser.parse_args(argv)
    data = Path(args.data) if args.data else default_data_folder()
    if args.status:
        print(status(data))
        return 0
    if not args.files and not args.lookup:
        parser.error("give one or more files, or --lookup WORD")
    try:
        dictionary = load_dictionary(Path(args.dictionary) if args.dictionary
                                     else data / DICTIONARY_FILE)
    except DictionaryError as e:
        print(e)
        return 2
    try:
        lists = []
        for given, default, own in ((args.general_words, GENERAL_WORDS, False),
                                    (args.words, data / WORDS_FILE, True)):
            path = Path(given) if given else default
            if given and not path.exists():
                print("No word list at %s." % path)
                return 2
            if path.exists():
                lists.append((path, ProjectWords.parse(read_file(path)), own))
        words = ProjectWords([e for _, part, _ in lists for e in part.entries])
        if args.lookup:
            for word in args.lookup:
                print(lookup(word, dictionary, words))
            return 0
        texts = [(path, read_file(path)) for path in args.files]
    except ReadError as e:
        print(e)
        return 2
    # The user cannot change the general word list, so only their own list gives findings.
    results = [(path, part.validate(dictionary)) for path, part, own in lists if own]
    results += [(path, check_text(text, dictionary, words)) for path, text in texts]
    errors = reviews = 0
    unknown = False
    for path, findings in results:
        for f in findings:
            print("%s:%s: %s Rule %s: %s" % (path, f.line, f.level, f.rule, f.message))
            errors += f.level == "ERROR"
            reviews += f.level == "REVIEW"
            unknown = unknown or UNKNOWN in f.message
    if unknown:
        print(UNKNOWN_HELP)
    print("STE check: %d errors, %d items to review." % (errors, reviews))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
