"""Build the STE word data file from the ASD-STE100 PDF.

Usage:
    python3 -I build_dictionary.py <asd-ste100.pdf or pdf_lines.js output> [output.json]

A PDF is read with macOS PDFKit through pdf_lines.js, which gives each line of
text with its position. The dictionary is a table with four columns (word,
meaning or alternatives, STE example, non-STE example), and the positions show
the column of each line. Without output.json, the output goes to
ste100-dictionary.json in the data folder of the plugin: $CLAUDE_PLUGIN_DATA,
or ~/.claude/plugins/data/writing-ste-claude-kit. The dictionary is ASD
copyright: keep the output on this computer and do not publish it.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ID = "writing-ste-claude-kit"
DICTIONARY_FILE = "ste100-dictionary.json"
NOTICE = ("Extracted from the ASD-STE100 PDF for local checks only. "
          "Copyright ASD. Do not publish or share this file.")

POS = r"n|v|adj|adv|pron|art|prep|conj"
PAGE_RE = re.compile(r"^=== PAGE (\d+) ===$")
ROW_RE = re.compile(r"^(-?\d+)\t(-?\d+)\t(.*)$")
LABEL_RE = re.compile(r"Page (2-\d+-[A-Z]?\d+)")
NOISE_RE = re.compile(
    r"^(ASD.?STE100 Simplified Technical English|Word Approved meaning/|Word"
    r"|\(part of speech\).*|Approved meaning/|ALTERNATIVES"
    r"|STE EXAMPLE Non-STE example|\d{4}-\d{2}-\d{2}|Blank Page"
    r"|.*Part 2 - Dictionary.*)$")
HEADER_RE = re.compile(
    r"^(?P<word>[A-Za-z][A-Za-z'’\-]*(?: (?:[A-Za-z][A-Za-z'’\-]*|\.\.\.|…\.?))*)"
    r"(?: \([A-Za-z ]+\))? \((?P<pos>" + POS + r")\)(?P<comma>,?)(?: (?P<rest>.*))?$")
# The first line of a header that continues on the next line of column 1.
HEADER_START_RE = re.compile(r"^[A-Za-z][A-Za-z'’\- ]*(?: \([A-Za-z ]+\))?$|-$")
ALT_RE = re.compile(
    r"([A-Z][A-Z'’\-]*(?: [A-Z][A-Z'’\-]*)*) \((" + POS + r"|TN|TV)\)")
ALT_START_RE = re.compile(r"^[A-Z][A-Z'’\- ]* \((?:" + POS + r"|TN|TV)\)")
FORM = r"[A-Z][A-Z'’\-]*(?: [A-Z][A-Z'’\-]*)*"
FORMS_RE = re.compile(r"^" + FORM + r"(?:, ?" + FORM + r")*,?$")
SINGLE_FORM_RE = re.compile(r"^[A-Z][A-Z'’\-]*,?$")
MAX_PHRASE_WORDS = 3  # a longer uppercase line in column 2 can include example text
ALSO_RE = re.compile(r"^\(also ([A-Z ,'’\-]+)\)$")
MEANING_START_RE = re.compile(r"^(\d+\.\s+)?(A |[A-Z])[a-z]|^[a-z(]")
NUMBERED_RE = re.compile(r"^\d+\.\s")
OTHER_MEANINGS_RE = re.compile(r"^For other")
NOTE_RE = re.compile(r"^(Use this word|Do not use this|This word)")
HELP_RE = re.compile(r"^(For other|Use this word|Do not use this|This word|No other)")
TITLE_RE = re.compile(r"ISSUE (\d+), ([A-Z]+ \d{4})")
SAME_ROW = 3  # points: text in other columns of the header row can be this much higher
SAME_CELL = 13  # points: the largest line spacing in one cell of column 1


def is_upper_text(s):
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def is_meaning_text(s):
    return bool(MEANING_START_RE.match(s)) and not is_upper_text(s)


def column(x, margin):
    offset = x - margin
    return 1 if offset < 60 else 2 if offset < 170 else 3 if offset < 300 else 4


def dictionary_pages(text):
    """Yield (page label, rows) for each page of the dictionary part.

    Each row is (column, y, text). Odd and even pages have different margins,
    so the columns come from the left margin of each page.
    """
    pages, current = [], None
    for raw in text.splitlines():
        if PAGE_RE.match(raw):
            current = []
            pages.append(current)
            continue
        m = ROW_RE.match(raw)
        if m and current is not None:
            current.append((int(m.group(1)), int(m.group(2)), m.group(3).strip()))
    for rows in pages:
        labels = [m.group(1) for m in (LABEL_RE.search(t) for _, _, t in rows) if m]
        if not labels or not labels[0].startswith("2-1-"):
            continue
        content = [(x, y, t) for x, y, t in rows if t and not NOISE_RE.match(t)]
        if content:
            margin = min(x for x, _, _ in content)
            yield labels[0], [(column(x, margin), y, t) for x, y, t in content]


def headers_on(rows):
    """Return (y, match, rows used) for each entry header in column 1.

    A long header can continue on the next line of column 1: "WOBBLESOME" and
    "(adj)", "SKYWARDISH" and "ZAP (prep)", or "UNWOBBLIFI-" and "CATED (adj)".
    The next line of the same cell is 12 or 13 points lower. The next entry
    is at least 17 points lower, so a list of verb forms is never joined with it.
    """
    col1 = sorted((r for r in rows if r[0] == 1), key=lambda r: -r[1])
    headers, used = [], set()
    for i, row in enumerate(col1):
        if row in used:
            continue
        text, rows_used = row[2], {row}
        if (i + 1 < len(col1) and row[1] - col1[i + 1][1] <= SAME_CELL
                and HEADER_START_RE.search(text) and not HEADER_RE.match(text)):
            nxt = col1[i + 1][2]
            joined = text[:-1] + nxt if text.endswith("-") else text + " " + nxt
            if HEADER_RE.match(joined):
                text = joined
                rows_used.add(col1[i + 1])
        m = HEADER_RE.match(text)
        if m and (m.group("word")[0].islower() or is_upper_text(m.group("word"))):
            headers.append((row[1], m, rows_used))
            used |= rows_used
    return headers


def split_forms(s):
    """Return the forms in a line such as "ZOOMS UP," or "(GRONKER, GRONKEST)"."""
    forms = (f.strip(" ()").lower().replace("’", "'") for f in s.split(","))
    return [f for f in forms if f]


def meaning_part(s):
    """Return the meaning text before the start of an uppercase example."""
    words = s.split()
    kept = []
    for i, w in enumerate(words):
        if is_upper_text(w) and (i + 1 == len(words) or is_upper_text(words[i + 1])):
            break
        kept.append(w)
    return " ".join(kept)


def read_forms(m, rest, col1):
    """Return the forms that column 1 lists under an approved word."""
    forms, i = [], 0
    pos = m.group("pos")
    if pos == "v":
        # With a comma after "(v)", the last form has no comma. Without one,
        # the forms (if any) are up to three lines of one uppercase word.
        comma = bool(m.group("comma"))
        while (comma or not rest) and i < len(col1) and FORMS_RE.match(col1[i]):
            if not comma and not SINGLE_FORM_RE.match(col1[i]):
                break
            forms += split_forms(col1[i])
            i += 1
            if (comma and not col1[i - 1].endswith(",")) or (not comma and i == 3):
                break
        if i < len(col1) and ALSO_RE.match(col1[i]):
            forms += split_forms(ALSO_RE.match(col1[i]).group(1))
    elif pos in ("adj", "adv"):
        # The forms are in parentheses, on the header line or under it. They can
        # continue on the next lines of column 1: "GRONK (adj) (GRONKER," and "GRONKEST)".
        if rest.startswith("("):
            lines = [rest[:rest.find(")") + 1] if ")" in rest else rest] + col1
        elif col1 and col1[0].startswith("("):
            lines = col1
        else:
            lines = []
        for line in lines:
            if not is_upper_text(line):
                break
            forms += split_forms(line)
            if ")" in line:
                break
    return forms


def read_meaning(rest, col2):
    """Return the first approved meaning: the header text, then column 2."""
    if rest.startswith("(") and ")" in rest:
        rest = rest[rest.find(")") + 1:].strip()
    parts = [meaning_part(rest)] if is_meaning_text(rest) else []
    for line in col2:
        if (is_upper_text(line) or HELP_RE.match(line) or ALT_START_RE.match(line)
                or (parts and NUMBERED_RE.match(line))):
            break
        part = meaning_part(line)
        if part:
            parts.append(part)
    return " ".join(p for p in parts if p)[:200]


def read_note(col2):
    for k, line in enumerate(col2):
        if NOTE_RE.match(line):
            parts = [line]
            for later in col2[k + 1:k + 8]:
                if parts[-1].endswith("."):
                    break
                if not is_upper_text(later):
                    parts.append(later)
            return " ".join(parts)
    return ""


def alternatives_in(lines):
    found = []
    for line in lines:
        for alt in ALT_RE.finditer(line):
            text = "%s (%s)" % (alt.group(1), alt.group(2))
            if text not in found:
                found.append(text)
    return found


def phrase_alternatives(col2):
    """Return short uppercase phrases in column 2, such as "NOT ZIBBY"."""
    return [line for line in col2 if is_upper_text(line) and "(" not in line
            and len(line.split()) <= MAX_PHRASE_WORDS]


def help_text(rest, col2):
    """Return the help text of a not approved word, without the examples."""
    lines = ([rest] if is_meaning_text(rest) else []) + [
        line for line in col2 if not is_upper_text(line) and not ALT_START_RE.match(line)]
    return " ".join(p for p in map(meaning_part, lines) if p)


def build_entry(m, label, body):
    """Return the dictionary entry for one header and the rows under it."""
    word = m.group("word").lower().replace("’", "'")
    rest = (m.group("rest") or "").strip()
    col1 = [t for c, _, t in body if c == 1]
    col2 = [t for c, _, t in body if c == 2]
    if m.group("word")[0].islower():
        alternatives = alternatives_in([rest] + col2)
        alternatives += [p for p in phrase_alternatives(col2) if p not in alternatives]
        return "not_approved", {"word": word, "pos": m.group("pos"),
                                "alternatives": alternatives,
                                "note": help_text(rest, col2),
                                "page": label}
    forms = read_forms(m, rest, col1)
    forms = [f for i, f in enumerate(forms) if f != word and f not in forms[:i]]
    other = next((k for k, line in enumerate(col2) if OTHER_MEANINGS_RE.match(line)), None)
    return "approved", {
        "word": word,
        "pos": m.group("pos"),
        "forms": forms,
        "meaning": read_meaning(rest, col2),
        "restricted": other is not None,
        "other_meanings": alternatives_in(col2[other:]) if other is not None else [],
        "note": read_note(col2),
        "page": label,
    }


def parse_dictionary_text(text):
    """Parse the output of pdf_lines.js into approved and not approved words."""
    entries = []  # [match, page label, header y, body rows]
    for label, rows in dictionary_pages(text):
        headers = headers_on(rows)
        used = set().union(*(h[2] for h in headers)) if headers else set()
        page_entries = [[m, label, y, []] for y, m, _ in headers]
        for row in sorted((r for r in rows if r not in used), key=lambda r: (-r[1], r[0])):
            owners = [e for e in page_entries if e[2] + SAME_ROW >= row[1]]
            owner = owners[-1] if owners else (entries[-1] if entries else None)
            if owner is not None:
                owner[3].append(row)
        entries += page_entries
    data = {"approved": [], "not_approved": []}
    for m, label, _, body in entries:
        kind, entry = build_entry(m, label, body)
        data[kind].append(entry)
    return data


class PdfError(Exception):
    """The script cannot read the PDF file. The text tells why."""


def pdf_lines(pdf):
    """Return the lines of the PDF file from pdf_lines.js. Raise PdfError if osascript fails."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lines.txt"
        try:
            subprocess.run(["osascript", "-l", "JavaScript", str(HERE / "pdf_lines.js"),
                            str(pdf), str(out)], check=True, capture_output=True, text=True)
        except FileNotFoundError:
            raise PdfError("The osascript command is not on this computer. The script can read"
                           " the PDF file only on macOS.") from None
        except subprocess.CalledProcessError as e:
            raise PdfError("osascript cannot read %s:\n%s" % (
                pdf, e.stderr.strip() or "exit status %d" % e.returncode)) from None
        return out.read_text(encoding="utf-8")


def default_data_folder():
    """Return the data folder of the plugin, which stays after each update."""
    if os.environ.get("CLAUDE_PLUGIN_DATA"):
        return Path(os.environ["CLAUDE_PLUGIN_DATA"])
    return Path.home() / ".claude" / "plugins" / "data" / PLUGIN_ID


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2):
        print(__doc__)
        return 2
    source = Path(args[0])
    output = Path(args[1]) if len(args) == 2 else default_data_folder() / DICTIONARY_FILE
    if not source.is_file():
        print("No file at %s. Give the path of the ASD-STE100 PDF file." % source)
        return 2
    try:
        text = (pdf_lines(source) if source.suffix.lower() == ".pdf"
                else source.read_text(encoding="utf-8"))
    except PdfError as e:
        print("%s\nThe dictionary file did not change." % e)
        return 2
    title = TITLE_RE.search(text)
    data = parse_dictionary_text(text)
    if not data["approved"] or not data["not_approved"]:
        # A PDF that is not the dictionary gives no entries. Keep the previous file.
        print("No dictionary entries in %s. The dictionary file did not change." % source)
        return 2
    result = {
        "source": "ASD-STE100 Issue %s, %s" % title.groups() if title else "ASD-STE100",
        "notice": NOTICE,
        "approved": data["approved"],
        "not_approved": data["not_approved"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("%d approved words (%d entries), %d words that are not approved -> %s" % (
        len({e["word"] for e in data["approved"]}), len(data["approved"]),
        len({e["word"] for e in data["not_approved"]}), output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
