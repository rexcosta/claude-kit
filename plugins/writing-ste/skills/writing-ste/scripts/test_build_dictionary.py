import ast
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_dictionary
import ste_check
from build_dictionary import parse_dictionary_text

HERE = Path(__file__).resolve().parent
DATA = build_dictionary.default_data_folder() / build_dictionary.DICTIONARY_FILE

# Offsets of the four dictionary columns from the left margin of a page:
# word, meaning or alternatives, STE example, non-STE example.
COLUMNS = {1: 0, 2: 108, 3: 238, 4: 367}


def page(number, label, *rows, margin=72):
    """Return one dictionary page in the format of pdf_lines.js.

    Each row is (column, y, text). Odd and even pages have different margins.
    """
    lines = ["=== PAGE %d ===" % number,
             "207\t739\tASD-STE100 Simplified Technical English",
             "%d\t716\tWord Approved meaning/" % margin,
             "%d\t704\t(part of speech) ALTERNATIVES STE EXAMPLE Non-STE example" % margin]
    lines += ["%d\t%d\t%s" % (margin + COLUMNS[c], y, text) for c, y, text in rows]
    lines += ["%d\t40\tIssue 9 Part 2 - Dictionary Page %s" % (margin + 300, label),
              "%d\t28\t2025-01-15" % (margin + 370)]
    return "\n".join(lines)


class ParseDictionaryTest(unittest.TestCase):
    def entry(self, data, kind, word, pos):
        for e in data[kind]:
            if e["word"] == word and e["pos"] == pos:
                return e
        self.fail("no %s entry for %s (%s)" % (kind, word, pos))

    def test_lowercase_header_is_a_not_approved_word_with_its_alternatives(self):
        data = parse_dictionary_text(page(
            149, "2-1-X1",
            (1, 643, "zarbit (prep) NEB OF (prep) THE GRIMBLE BOX IS"),
            (3, 631, "FASTENED NEB OF"), (3, 619, "THE WOBBLE"),
            (3, 607, "SHELF."), (4, 643, "The grimble box is"),
            (4, 631, "fastened zarbit the wobble"), (4, 619, "shelf.")))
        e = self.entry(data, "not_approved", "zarbit", "prep")
        self.assertEqual(e["alternatives"], ["NEB OF (prep)"])
        self.assertEqual(e["page"], "2-1-X1")

    def test_uppercase_word_in_the_second_column_is_an_alternative(self):
        data = parse_dictionary_text(page(
            149, "2-1-X1",
            (1, 588, "flonder (v) ZOOP (v) IF THERE IS A GLOOP,"),
            (4, 588, "If there is a gloop,"), (3, 576, "QUICKLY ZOOP TO"),
            (4, 576, "quickly flonder"), (3, 564, "A DRY ZONE."),
            (4, 564, "the zone."), (2, 546, "KLUNK (v)"),
            (3, 546, "IF THE NUMBERS ARE"), (4, 546, "If the numbers are"),
            (3, 534, "WRONG, KLUNK"), (4, 534, "wrong, flonder the"),
            (3, 522, "THE CHECK"), (4, 522, "check list."), (3, 510, "LIST.")))
        self.assertEqual(data["approved"], [])
        e = self.entry(data, "not_approved", "flonder", "v")
        self.assertEqual(e["alternatives"], ["ZOOP (v)", "KLUNK (v)"])

    def test_approved_verb_keeps_its_forms_and_its_meaning_ends_at_the_next_entry(self):
        data = parse_dictionary_text(page(
            156, "2-1-X2",
            (1, 322, "FROBULATE (v),"), (1, 310, "FROBULATES,"), (1, 298, "FROBULATED,"),
            (1, 286, "FROBULATED"), (2, 321, "To set a dial or move it to a"),
            (2, 309, "marked point or"), (2, 297, "level"),
            (3, 321, "FROBULATE THE"), (3, 309, "DIAL TO THE"),
            (3, 297, "LEVEL IN"), (3, 285, "LIST 2."),
            (1, 212, "FROBULATABLE (adj)"), (2, 211, "That can be frobulated"),
            margin=50))
        e = self.entry(data, "approved", "frobulate", "v")
        self.assertEqual(e["forms"], ["frobulates", "frobulated"])
        self.assertEqual(e["meaning"],
                         "To set a dial or move it to a marked point or level")
        self.assertEqual(self.entry(data, "approved", "frobulatable", "adj")["meaning"],
                         "That can be frobulated")

    def test_approved_adjective_keeps_its_comparative_forms(self):
        data = parse_dictionary_text(page(
            295, "2-1-X3",
            (1, 383, "GRONK (adj)"), (1, 371, "(GRONKER,"), (1, 359, "GRONKEST)"),
            (2, 382, "With more bumps than"), (2, 370, "a flat, smooth, or"),
            (2, 358, "plain surface"), (3, 382, "SAND THE GRONK"),
            (3, 370, "PANEL WITH A"), (3, 358, "SOFT CLOTH AND"), (3, 346, "OIL.")))
        e = self.entry(data, "approved", "gronk", "adj")
        self.assertEqual(e["forms"], ["gronker", "gronkest"])
        self.assertEqual(e["meaning"],
                         "With more bumps than a flat, smooth, or plain surface")

    def test_comparative_forms_that_start_on_the_header_line_continue_on_the_next_line(self):
        data = parse_dictionary_text(page(
            295, "2-1-X3",
            (1, 383, "GRONK (adj) (GRONKER,"), (1, 371, "GRONKEST)"),
            (2, 382, "With more bumps than"), (2, 370, "a flat surface"),
            (3, 382, "SAND THE GRONK"), (3, 370, "PANEL.")))
        self.assertEqual(self.entry(data, "approved", "gronk", "adj")["forms"],
                         ["gronker", "gronkest"])

    def test_comparative_forms_stop_at_a_line_that_is_not_uppercase(self):
        data = parse_dictionary_text(page(
            295, "2-1-X3",
            (1, 383, "GRONK (adj) (GRONKER,"), (1, 371, "No other forms"),
            (2, 382, "With more bumps than"), (3, 382, "SAND THE GRONK")))
        self.assertEqual(self.entry(data, "approved", "gronk", "adj")["forms"], ["gronker"])

    def test_be_keeps_the_forms_in_the_also_line(self):
        data = parse_dictionary_text(page(
            175, "2-1-X4",
            (1, 686, "ZEB (v),"), (1, 674, "ZIZ, ZAZ,"), (1, 662, "(also ZAR, ZER)"),
            (1, 643, "No other forms"), (1, 631, "of this verb."),
            (2, 685, "1. To float, drift IF THERE IS"), (3, 673, "FOAM ON THE"),
            (3, 661, "TANK LID,"), (3, 649, "CLEAN THE LID."),
            (2, 613, "2. To have a color,"), (2, 601, "to look like")))
        e = self.entry(data, "approved", "zeb", "v")
        self.assertEqual(e["forms"], ["ziz", "zaz", "zar", "zer"])
        self.assertEqual(e["meaning"], "1. To float, drift")

    def test_approved_word_with_other_meanings_is_restricted(self):
        data = parse_dictionary_text(page(
            150, "2-1-X5",
            (1, 685, "ZUBBLE (prep) Related to a zib"),
            (3, 685, "FOR DATA ZUBBLE THE"), (3, 673, "PLACE OF THE"),
            (3, 661, "BLUE LEVERS, REFER TO"), (3, 649, "THE LEVER LIST."),
            (2, 655, "For other meanings,"), (2, 643, "use these words:"),
            (2, 625, "GLOMMISH (adv) POUR"), (3, 613, "GLOMMISH"),
            (3, 601, "3 CUPS OF OIL"), (3, 589, "FROM THE JUG."),
            (4, 625, "Pour zubble 3 cups of"), (4, 613, "oil from the jug."),
            (2, 570, "GLUMWISE (prep) SPIN THE WHEEL"), (3, 558, "GLUMWISE ITS HUB."),
            (4, 570, "Spin the wheel zubble its"), (4, 558, "hub."),
            (1, 540, "ZOVER (prep) In (or near) a place"),
            (2, 528, "higher on the shelf than"), (2, 516, "the box"),
            margin=50))
        zubble = self.entry(data, "approved", "zubble", "prep")
        self.assertTrue(zubble["restricted"])
        self.assertEqual(zubble["meaning"], "Related to a zib")
        self.assertEqual(zubble["other_meanings"],
                         ["GLOMMISH (adv)", "GLUMWISE (prep)"])
        zover = self.entry(data, "approved", "zover", "prep")
        self.assertFalse(zover["restricted"])
        self.assertEqual(zover["meaning"],
                         "In (or near) a place higher on the shelf than the box")
        self.assertEqual(sorted(e["word"] for e in data["approved"]),
                         ["zover", "zubble"])

    def test_help_note_is_kept_apart_from_the_meaning(self):
        data = parse_dictionary_text(page(
            396, "2-1-X6",
            (1, 316, "GULPLE (v),"), (1, 304, "GULPLES,"), (1, 292, "GULPLED,"),
            (1, 280, "GULPLED"), (3, 315, "IF YOU GULPLE"),
            (3, 303, "BLUE SODA, DO NOT"), (3, 291, "RUN FAST."),
            (3, 279, "SIT DOWN"), (3, 267, "AT ONCE."),
            (2, 315, "To move a drink from the"), (2, 303, "cup through the throat"),
            (2, 291, "into the belly"), (2, 273, "Use this word only"),
            (2, 261, "for soda and"), (2, 249, "juice."),
            margin=50))
        e = self.entry(data, "approved", "gulple", "v")
        self.assertEqual(e["meaning"],
                         "To move a drink from the cup through the throat into the belly")
        self.assertEqual(e["note"], "Use this word only for soda and juice.")

    def test_meaning_that_starts_with_the_article_a_is_kept(self):
        data = parse_dictionary_text(page(
            155, "2-1-X7",
            (1, 500, "ZINGY (adj) A lamp, fan, or"),
            (2, 488, "pump that has power and"), (2, 476, "turns"),
            (3, 500, "THE LAMP IS"), (3, 488, "ZINGY.")))
        e = self.entry(data, "approved", "zingy", "adj")
        self.assertEqual(e["meaning"],
                         "A lamp, fan, or pump that has power and turns")

    def test_verb_forms_without_commas_are_read(self):
        data = parse_dictionary_text(page(
            320, "2-1-X8",
            (1, 400, "SNORKLE (v)"), (1, 388, "SNORKLES"), (1, 376, "SNORKLED"),
            (1, 364, "SNORKLED"), (2, 400, "To push air out of a"),
            (2, 388, "tube or a long"), (2, 376, "hose"),
            (3, 400, "IF THE RED-TOP"), (3, 388, "FLAG"),
            (3, 376, "SNORKLES,"), (3, 364, "CLEAN THE TUBE")))
        e = self.entry(data, "approved", "snorkle", "v")
        self.assertEqual(e["forms"], ["snorkles", "snorkled"])
        self.assertEqual(e["meaning"],
                         "To push air out of a tube or a long hose")

    def test_header_with_the_part_of_speech_on_the_next_line(self):
        data = parse_dictionary_text(page(
            153, "2-1-X9",
            (1, 686, "WOBBLESOME"), (1, 674, "(adj)"),
            (2, 685, "That moves from side to"), (2, 673, "side"),
            (3, 685, "TO STOP"), (3, 673, "WOBBLESOME"),
            (3, 661, "MOVEMENT OF THE")))
        e = self.entry(data, "approved", "wobblesome", "adj")
        self.assertEqual(e["meaning"], "That moves from side to side")

    def test_header_that_wraps_with_a_hyphen(self):
        data = parse_dictionary_text(page(
            417, "2-1-X10",
            (1, 341, "UNWOBBLIFI-"), (1, 329, "CATED (adj)"),
            (2, 340, "Not wobbly at all"), (3, 340, "IF THE STATE OF"),
            (3, 328, "THE WHEELS IS")))
        e = self.entry(data, "approved", "unwobblificated", "adj")
        self.assertEqual(e["meaning"], "Not wobbly at all")

    def test_header_with_two_words_on_two_lines(self):
        data = parse_dictionary_text(page(
            223, "2-1-X11",
            (1, 474, "SKYWARDISH"), (1, 462, "ZAP (prep)"),
            (2, 473, "In the way that the"), (2, 461, "wind goes"),
            (3, 473, "LOCK THE")))
        self.assertEqual([(e["word"], e["pos"], e["meaning"]) for e in data["approved"]],
                         [("skywardish zap", "prep", "In the way that the wind goes")])

    def test_last_form_of_a_verb_is_not_joined_with_the_next_header(self):
        data = parse_dictionary_text(page(
            320, "2-1-X8",
            (1, 400, "SNORKLE (v)"), (1, 388, "SNORKLES"), (1, 376, "SNORKLED"),
            (1, 364, "SNORKLED"), (2, 400, "To push air out"),
            (1, 345, "FLIBBER (v),"), (1, 333, "FLIBBERS,"), (1, 321, "FLIBBERED,"),
            (1, 309, "FLIBBERED"), (2, 345, "To hand over")))
        self.assertEqual([(e["word"], e["forms"]) for e in data["approved"]],
                         [("snorkle", ["snorkles", "snorkled"]),
                          ("flibber", ["flibbers", "flibbered"])])

    def test_short_uppercase_phrase_in_the_second_column_is_an_alternative(self):
        data = parse_dictionary_text(page(
            217, "2-1-X12",
            (1, 546, "grumbly (adj)"), (2, 546, "NOT ZIBBY"),
            (3, 546, "IF IT IS NOT ZIBBY TO"), (4, 546, "If the hinge pin is"),
            (2, 491, "NOT ZIBBILY IF YOU CANNOT"), (3, 479, "TURN THE HINGE")))
        self.assertEqual(self.entry(data, "not_approved", "grumbly", "adj")["alternatives"],
                         ["NOT ZIBBY"])

    def test_help_text_of_a_not_approved_word_is_kept(self):
        data = parse_dictionary_text(page(
            238, "2-1-X13",
            (1, 261, "snubbit (prep) Write the sentence"), (2, 249, "again with a"),
            (2, 237, "new"), (2, 225, "form."), (2, 213, "Keep it short."),
            (3, 261, "KEEP ALL THE BOLTS"), (3, 249, "THAT YOU HAVE"),
            margin=50))
        e = self.entry(data, "not_approved", "snubbit", "prep")
        self.assertEqual(e["alternatives"], [])
        self.assertEqual(e["note"],
                         "Write the sentence again with a new form. Keep it short.")

    def test_verb_forms_with_two_words(self):
        data = parse_dictionary_text(page(
            194, "2-1-X14",
            (1, 463, "ZOOM UP (v),"), (1, 451, "ZOOMS UP,"), (1, 439, "ZAMMED UP"),
            (1, 419, "No other forms"), (1, 407, "of this verb."),
            (2, 461, "To start to shine with"), (3, 461, "THE LAMPS MUST"),
            margin=50))
        self.assertEqual(self.entry(data, "approved", "zoom up", "v")["forms"],
                         ["zooms up", "zammed up"])

    def test_header_with_an_or_qualifier_and_the_part_of_speech_on_the_next_line(self):
        data = parse_dictionary_text(page(
            301, "2-1-X15",
            (1, 262, "FLUB (or FLUBB)"), (1, 250, "(adj)"),
            (2, 261, "Not shiny PUT FLUB WAX"), (3, 249, "ON THE DOOR."),
            margin=50))
        self.assertEqual(self.entry(data, "approved", "flub", "adj")["meaning"], "Not shiny")

    def test_meaning_that_comes_after_the_example_in_the_text(self):
        data = parse_dictionary_text(page(
            401, "2-1-X16",
            (1, 578, "ZORK (n)"), (3, 578, "REMOVE ALL THE"),
            (3, 566, "PARTS THAT ARE"), (3, 554, "NOT NEEDED FOR"),
            (3, 542, "THE ZORK."), (2, 578, "The method where a"),
            (2, 566, "box or a lamp is"), (2, 554, "turned on to find out"),
            (2, 542, "if its light"), (2, 529, "and/or sound is good"),
            (1, 511, "zork (v) ZORK (n) DO A FULL"), (3, 499, "ZORK OF THE")))
        e = self.entry(data, "approved", "zork", "n")
        self.assertEqual(e["meaning"],
                         "The method where a box or a lamp is turned on to find out"
                         " if its light and/or sound is good")
        self.assertEqual(self.entry(data, "not_approved", "zork", "v")["alternatives"],
                         ["ZORK (n)"])

    def test_entry_continues_on_the_next_page(self):
        text = page(149, "2-1-X1",
                    (1, 100, "glorp (v) SHRONK (v) WHEN THE FOG"),
                    (3, 88, "LEVEL SHRONKS")) + "\n" + page(
                    150, "2-1-X2",
                    (2, 700, "KWIT (v) THE FOG KWITS."),
                    (1, 650, "glorpness (n) MIBBLE (v) ONE PUMP"),
                    margin=50)
        data = parse_dictionary_text(text)
        self.assertEqual(self.entry(data, "not_approved", "glorp", "v")["alternatives"],
                         ["SHRONK (v)", "KWIT (v)"])
        self.assertEqual(self.entry(data, "not_approved", "glorpness", "n")["alternatives"],
                         ["MIBBLE (v)"])

    def test_headers_with_a_qualifier_or_an_ellipsis(self):
        data = parse_dictionary_text(page(
            249, "2-1-X17",
            (1, 394, "zib (a zib) (adj) ZOME (adj) LET THE PUMP"),
            (1, 231, "ZO ... ZO (conj)"), (2, 230, "Link word: put before")))
        self.assertEqual(self.entry(data, "not_approved", "zib", "adj")["alternatives"],
                         ["ZOME (adj)"])
        self.entry(data, "approved", "zo ... zo", "conj")

    def test_pages_outside_the_dictionary_part_are_ignored(self):
        data = parse_dictionary_text(page(
            131, "2-0-3",
            (1, 600, "ZAP (n) A help that you get IF YOU ZAP THIS"),
            (1, 500, "zappiness (n) ZAPNESS (n) THE ZAPNESS OF")))
        self.assertEqual(data["approved"], [])
        self.assertEqual(data["not_approved"], [])


class MainTest(unittest.TestCase):
    def test_output_goes_to_the_data_folder_when_the_command_gives_no_output_path(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": tmp}):
            lines = Path(tmp) / "lines.txt"
            lines.write_text(page(149, "2-1-X1", (1, 643, "zorbel (v) FLIM (v) THE ZORBEL IS"),
                                  (1, 600, "FLIM (v)"), (2, 600, "To turn a dial")),
                             encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = build_dictionary.main([str(lines)])
            data = json.loads((Path(tmp) / "ste100-dictionary.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual([e["word"] for e in data["not_approved"]], ["zorbel"])
        self.assertEqual([e["word"] for e in data["approved"]], ["flim"])

    def build_into(self, source):
        """Do main() with this source and a previous dictionary file.

        Give the code, the file text, and the output.
        """
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": tmp}):
            output = Path(tmp) / "ste100-dictionary.json"
            output.write_text("previous", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = build_dictionary.main([source(Path(tmp))])
            return code, output.read_text(encoding="utf-8"), out.getvalue()

    def build_from_pdf(self, osascript=None):
        """Do main() with a PDF file. osascript: the text of the osascript command, or None for no command."""
        def pdf(tmp):
            commands = tmp / "bin"
            commands.mkdir()
            if osascript is not None:
                (commands / "osascript").write_text(osascript, encoding="utf-8")
                (commands / "osascript").chmod(0o755)
            os.environ["PATH"] = str(commands)
            (tmp / "ste.pdf").write_bytes(b"%PDF-1.4\n")
            return str(tmp / "ste.pdf")
        with mock.patch.dict(os.environ):
            return self.build_into(pdf)

    def test_build_with_a_missing_pdf_keeps_the_dictionary_file(self):
        self.assertEqual(self.build_into(lambda tmp: str(tmp / "missing.pdf"))[:2],
                         (2, "previous"))

    def test_build_that_finds_no_entries_keeps_the_dictionary_file(self):
        def outside(tmp):
            lines = tmp / "lines.txt"
            lines.write_text(page(131, "2-0-3", (1, 600, "ZAP (n) A help")), encoding="utf-8")
            return str(lines)
        self.assertEqual(self.build_into(outside)[:2], (2, "previous"))

    def test_build_from_a_pdf_without_osascript_tells_that_it_needs_macos(self):
        code, previous, out = self.build_from_pdf(osascript=None)
        self.assertEqual((code, previous), (2, "previous"))
        self.assertIn("macOS", out)

    def test_build_from_a_pdf_that_osascript_cannot_read_shows_the_error_of_osascript(self):
        code, previous, out = self.build_from_pdf(
            osascript="#!/bin/sh\necho 'frob: the PDF file is locked' >&2\nexit 1\n")
        self.assertEqual((code, previous), (2, "previous"))
        self.assertIn("frob: the PDF file is locked", out)

    def test_the_two_scripts_use_the_same_default_data_folder(self):
        self.assertEqual(build_dictionary.default_data_folder(), ste_check.default_data_folder())


@unittest.skipUnless(DATA.exists(), "no dictionary data file")
class RealDictionaryTest(unittest.TestCase):
    """Checks of the data file that build_dictionary.py made from the real PDF."""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))

    def test_numbers_of_entries_are_near_the_numbers_in_the_introduction(self):
        # Part 2 gives 875 approved and 1274 not approved words, but not how it
        # counts them. A large difference shows that a part of the layout failed.
        self.assertAlmostEqual(len(self.data["approved"]), 875, delta=20)
        self.assertAlmostEqual(len(self.data["not_approved"]), 1274, delta=60)

    def test_each_one_word_alternative_is_an_approved_word_or_form(self):
        known = {e["word"] for e in self.data["approved"]}
        known |= {f for e in self.data["approved"] for f in e["forms"]}
        missing = set()
        for e in self.data["not_approved"]:
            for alt in e["alternatives"]:
                word, _, pos = alt.rpartition(" (")
                if word and " " not in word and pos[:-1] not in ("TN", "TV"):
                    if word.lower() not in known:
                        missing.add(word.lower())
        self.assertEqual(missing, set())

    def test_each_approved_entry_has_a_meaning(self):
        self.assertEqual([e["word"] for e in self.data["approved"] if not e["meaning"]], [])

    def test_the_test_files_contain_no_text_of_the_dictionary(self):
        texts = set()
        for kind in ("approved", "not_approved"):
            for e in self.data[kind]:
                texts.update([e.get("meaning") or "", e.get("note") or ""])
                texts.update(e.get("alternatives") or [])
                texts.update(e.get("other_meanings") or [])
        found = []
        for name in ("test_build_dictionary.py", "test_ste_check.py"):
            tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
            found += [n.value for n in ast.walk(tree)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)
                      and " " in n.value.strip() and n.value in texts]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
