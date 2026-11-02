import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ste_check import (GENERAL_WORDS, Dictionary, ProjectWords, check_text, default_data_folder,
                       main, plural_forms, regular_verb_forms)


def approved(word, pos, forms=(), meaning="", restricted=False,
             other_meanings=(), note="", page="2-1-X1"):
    return {"word": word, "pos": pos, "forms": list(forms), "meaning": meaning,
            "restricted": restricted, "other_meanings": list(other_meanings),
            "note": note, "page": page}


def not_approved(word, pos, alternatives, note="", page="2-1-X1"):
    return {"word": word, "pos": pos, "alternatives": list(alternatives),
            "note": note, "page": page}


DATA = {
    "approved": [
        approved("a", "art"), approved("the", "art"), approved("and", "conj"),
        approved("if", "conj"), approved("in", "prep"), approved("not", "adv"),
        approved("only", "adv"), approved("it", "pron"), approved("this", "pron"),
        approved("you", "pron"), approved("can", "v"),
        approved("glim", "prep", meaning="Near a blue valve", restricted=True,
                 other_meanings=["GLOM (adv)", "GLUM (prep)"]),
        approved("be", "v", ["is", "was", "are", "were"]),
        approved("close", "v", ["closes", "closed"]),
        approved("blip", "v", ["blips", "blipped"]),
        approved("do", "v", ["does", "did", "done"]),
        approved("open", "v", ["opens", "opened"]), approved("open", "adj"),
        approved("read", "v", ["reads", "read"]),
        approved("remove", "v", ["removes", "removed"]),
        approved("vosk", "v", ["vosks", "vosked"],
                 note="Use this word only for the red valve."),
        approved("activate", "v"),
        approved("come on", "v", ["comes on", "came on"]),
        approved("battery", "n"), approved("box", "n"), approved("cap", "n"),
        approved("file", "n"), approved("light", "n"), approved("valve", "n"),
    ],
    "not_approved": [
        not_approved("flarn", "v", ["ZORP (v)"]),
        not_approved("blip", "adj", ["SNIB (adj)"]),
        not_approved("trel", "adj", ["WUB (adj)"]),
        not_approved("snub", "prep", [], note="Write the sentence in a new form."),
    ],
}
DICTIONARY = Dictionary(DATA)

WORDS = """\
| Word | Type | Category | Forms | Note |
|---|---|---|---|---|
| Slack | TN | 11 | | The company that makes the Slack application |
| token | TN | 19 | | A secret that gives access to an API |
| time off | TN | 9 | | Time away from work |
| commit | TV | 2c | | Save changes in Git |
"""

FILLER = ["the", "cap", "and"]


def filler(n):
    return " ".join(FILLER[i % 3] for i in range(n))


def instruction(n):
    """An instruction of n words."""
    return "Remove " + filler(n - 1) + "."


def description(n):
    """A description of n words."""
    return "It is " + filler(n - 2) + "."


def check(text, words=""):
    return check_text(text, DICTIONARY, ProjectWords.parse(words))


def errors(findings):
    return [f for f in findings if f.level == "ERROR"]


def reviews(findings):
    return [f for f in findings if f.level == "REVIEW"]


SCRIPTS = Path(__file__).resolve().parent


def run(*argv):
    """Do main() with these parameters. Give the exit code and the output."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class DataFolderTest(unittest.TestCase):
    def test_default_data_folder_is_the_folder_of_the_marketplace_install(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_PLUGIN_DATA", None)
            self.assertEqual(default_data_folder(), Path.home() / ".claude" / "plugins"
                             / "data" / "writing-ste-claude-kit")

    def test_environment_variable_gives_the_data_folder(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": "/frob/data"}):
            self.assertEqual(default_data_folder(), Path("/frob/data"))


class StatusTest(unittest.TestCase):
    def status_of(self, content, folder="data"):
        """Do --status with a dictionary file that has this content. None: no file."""
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / folder
            data.mkdir()
            if content is not None:
                (data / "ste100-dictionary.json").write_text(content, encoding="utf-8")
            code, out = run("--status", "--data", str(data))
        return code, out, data

    def assertNotCorrect(self, code, out):
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("ERROR: The dictionary file is not correct:"), out)
        self.assertIn("build_dictionary.py", out)

    def test_correct_dictionary_gives_ok_and_the_source(self):
        code, out, data = self.status_of(json.dumps(dict(DATA, source="FROB Issue 1")))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("OK: "), out)
        self.assertIn("FROB Issue 1", out)
        self.assertIn(str(data), out)

    def test_missing_dictionary_gives_the_link_and_the_command(self):
        code, out, data = self.status_of(None)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("ERROR: The ASD-STE100 dictionary is not installed."), out)
        self.assertIn("https://www.asd-ste100.org", out)
        self.assertIn('python3 -I "%s" PDF "%s"' % (SCRIPTS / "build_dictionary.py",
                                                  data / "ste100-dictionary.json"), out)

    def test_dictionary_that_is_not_json_is_not_correct(self):
        self.assertNotCorrect(*self.status_of("{frob")[:2])

    def test_empty_dictionary_file_is_not_correct(self):
        self.assertNotCorrect(*self.status_of("")[:2])

    def test_dictionary_with_a_different_structure_is_not_correct(self):
        for content in ('[]', '{"approved": []}',
                        '{"approved": [{"pos": "n"}], "not_approved": []}'):
            with self.subTest(content=content):
                self.assertNotCorrect(*self.status_of(content)[:2])

    def test_dictionary_without_entries_is_not_correct(self):
        self.assertNotCorrect(*self.status_of('{"approved": [], "not_approved": []}')[:2])

    def test_dictionary_with_an_empty_word_is_not_correct(self):
        content = json.dumps({"approved": [approved("", "v")],
                              "not_approved": [not_approved("flarn", "v", ["ZORP (v)"])]})
        self.assertNotCorrect(*self.status_of(content)[:2])

    @unittest.skipIf(os.geteuid() == 0, "root can read a folder without permissions")
    def test_data_folder_without_read_permission_is_not_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            data.chmod(0)
            try:
                code, out = run("--status", "--data", str(data))
            finally:
                data.chmod(0o700)
        self.assertNotCorrect(code, out)

    def test_build_command_puts_quotation_marks_around_the_paths(self):
        _, out, data = self.status_of(None, folder="my data")
        self.assertIn('"%s"' % (data / "ste100-dictionary.json"), out)

    def test_empty_data_parameter_uses_the_default_data_folder(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": tmp}):
            code, out = run("--status", "--data", "")
        self.assertEqual(code, 0)
        self.assertIn(str(Path(tmp) / "ste100-dictionary.json"), out)

    def test_check_without_the_dictionary_shows_the_error_and_exits_with_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = Path(tmp) / "text.md"
            text.write_text("Remove the cap.\n", encoding="utf-8")
            code, out = run("--data", tmp, str(text))
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("ERROR: The ASD-STE100 dictionary is not installed."), out)


class WordTest(unittest.TestCase):
    def test_not_approved_word_is_an_error_that_gives_the_alternative(self):
        [f] = check("Flarn the valve.")
        self.assertEqual((f.level, f.rule, f.line), ("ERROR", "1.1", 1))
        self.assertIn("ZORP (v)", f.message)

    def test_word_that_is_not_in_the_dictionary_is_an_error(self):
        [f] = check("Frobnicate the valve.")
        self.assertEqual((f.level, f.rule), ("ERROR", "1.1"))
        self.assertIn("frobnicate", f.message)

    def test_listed_verb_forms_and_noun_plurals_are_approved(self):
        self.assertEqual(check("It removed the valves. It opens the boxes."), [])

    def test_regular_forms_of_a_verb_that_lists_no_forms_are_approved(self):
        self.assertEqual(check("It activates the valve. It activated the cap."), [])

    def test_approved_form_with_two_words_is_approved(self):
        self.assertEqual(check("If the light comes on, remove the cap."), [])

    def test_approved_form_with_two_words_on_two_lines_is_approved(self):
        self.assertEqual(check("If the light comes\non, remove the cap."), [])

    def test_not_approved_word_with_no_alternative_gives_the_help_text(self):
        [f] = check("Remove the cap snub the valve.")
        self.assertEqual(f.rule, "1.1")
        self.assertIn("new form", f.message)

    def test_ing_form_is_an_error_for_rule_3_5(self):
        [f] = check("It is removing the cap.")
        self.assertEqual((f.level, f.rule), ("ERROR", "3.5"))

    def test_unknown_word_that_ends_in_ing_is_not_called_a_verb_form(self):
        [f] = check("It is the meaning.")
        self.assertEqual(f.rule, "1.1")

    def test_number_words_are_technical_nouns_of_category_9(self):
        self.assertEqual(check("Remove the two caps and the twenty-one boxes."), [])

    def test_same_word_is_reported_once_with_all_its_lines(self):
        [f] = check("Frobnicate the valve.\n\nFrobnicate the cap.")
        self.assertEqual(f.line, 1)
        self.assertIn("1, 3", f.message)

    def test_possessive_form_is_permitted(self):
        self.assertEqual(check("Remove the valve's cap."), [])

    def test_hyphenated_word_is_approved_when_each_part_is_approved(self):
        self.assertEqual(check("Open the read-only file."), [])

    def test_hyphenated_word_reports_the_part_that_is_not_approved(self):
        [f] = check("Open the read-frob file.")
        self.assertIn("frob", f.message)

    def test_word_with_digits_is_an_identifier_that_is_not_checked(self):
        self.assertEqual(check("Open the ASD-STE100 file."), [])

    def test_identifier_with_digits_and_no_hyphen_is_not_checked(self):
        self.assertEqual(check("Open the STE100 file and the SHA256 file.\n\n"
                               "Remove the IPv6 cap and the 2FA valve."), [])

    def test_word_after_a_number_and_a_hyphen_is_checked(self):
        [f] = check("Open the 20-frob file.")
        self.assertIn('"frob"', f.message)

    def test_word_approved_only_as_a_different_part_of_speech_needs_review(self):
        findings = check("Blip the valve.")
        self.assertEqual(errors(findings), [])
        [r] = reviews(findings)
        self.assertEqual(r.rule, "1.2")
        self.assertIn("SNIB (adj)", r.message)

    def test_word_with_a_restricted_meaning_needs_review(self):
        [r] = check("It is glim the valve.")
        self.assertEqual((r.level, r.rule), ("REVIEW", "1.3"))
        self.assertIn("Near a blue valve", r.message)

    def test_word_with_a_help_note_needs_review(self):
        [r] = check("If you vosk the cap, do not remove it.")
        self.assertEqual(r.level, "REVIEW")
        self.assertIn("only for the red valve", r.message)


class ProjectWordsTest(unittest.TestCase):
    def test_technical_nouns_and_verbs_in_the_list_are_permitted(self):
        self.assertEqual(check("Commit the Slack file.", WORDS), [])

    def test_regular_forms_of_a_technical_verb_are_permitted(self):
        self.assertEqual(
            check("It committed the file. It commits the file.", WORDS), [])

    def test_plural_of_a_technical_noun_is_permitted(self):
        self.assertEqual(check("Remove the tokens.", WORDS), [])

    def test_technical_noun_with_more_than_one_word_is_permitted(self):
        self.assertEqual(check("Remove the time off.", WORDS), [])

    def test_technical_noun_with_two_words_on_two_lines_is_permitted(self):
        self.assertEqual(check("Remove the time\noff.", WORDS), [])

    def test_technical_verb_that_the_dictionary_does_not_approve_needs_review(self):
        words = WORDS + "| flarn | TV | 2c | | |\n"
        for text in ("Flarn the valve.", "It flarned the valve."):
            with self.subTest(text=text):
                findings = check(text, words)
                self.assertEqual(errors(findings), [])
                [r] = reviews(findings)
                self.assertEqual(r.rule, "1.12")
                self.assertIn("ZORP (v)", r.message)

    def test_technical_noun_that_the_dictionary_does_not_approve_only_as_an_adjective_is_permitted(self):
        self.assertEqual(check("Remove the trel.", WORDS + "| trel | TN | 19 | | |\n"), [])

    def test_valid_list_has_no_findings(self):
        self.assertEqual(ProjectWords.parse(WORDS).validate(DICTIONARY), [])

    def test_technical_noun_that_the_dictionary_gives_as_an_adjective_needs_review(self):
        words = WORDS + "| trel | TN | 19 | | |\n"
        [r] = ProjectWords.parse(words).validate(DICTIONARY)
        self.assertEqual(r.level, "REVIEW")
        self.assertIn("(adj)", r.message)

    def test_technical_noun_that_is_an_approved_noun_is_an_error(self):
        words = WORDS + "| valve | TN | 1 | | |\n"
        [f] = ProjectWords.parse(words).validate(DICTIONARY)
        self.assertEqual((f.level, f.line), ("ERROR", 7))

    def test_category_must_exist(self):
        words = WORDS + "| Jira | TN | 23 | | |\n| sync | TV | 5 | | |\n"
        findings = ProjectWords.parse(words).validate(DICTIONARY)
        self.assertEqual([(f.level, f.line) for f in findings],
                         [("ERROR", 7), ("ERROR", 8)])

    def test_type_must_be_tn_or_tv(self):
        words = WORDS + "| Jira | XX | 19 | | |\n"
        [f] = ProjectWords.parse(words).validate(DICTIONARY)
        self.assertEqual(f.level, "ERROR")


class SentenceTest(unittest.TestCase):
    def test_instruction_can_have_20_words(self):
        self.assertEqual(check(instruction(20)), [])

    def test_instruction_with_21_words_is_an_error(self):
        [f] = check(instruction(21))
        self.assertEqual((f.rule, f.line), ("5.1", 1))
        self.assertIn("21", f.message)

    def test_description_can_have_25_words(self):
        self.assertEqual(check(description(25)), [])

    def test_description_with_26_words_is_an_error(self):
        [f] = check(description(26))
        self.assertEqual(f.rule, "6.3")
        self.assertIn("26", f.message)

    def test_instruction_after_a_condition_uses_the_instruction_limit(self):
        [f] = check("If you open the valve, remove " + filler(15) + ".")
        self.assertEqual(f.rule, "5.1")

    def test_text_in_parentheses_counts_as_one_word(self):
        text = instruction(19)[:-1] + " (it is the cap and the valve)."
        self.assertEqual(check(text), [])

    def test_code_quoted_text_and_numbers_count_as_one_word_each(self):
        text = ('Remove `frob a b c d` and "x y z w" and 2,000 '
                + filler(14) + ".")
        self.assertEqual(check(text), [])

    def test_each_item_of_a_vertical_list_is_a_sentence(self):
        text = "Do this:\n\n- " + instruction(15) + "\n- " + instruction(15) + "\n"
        self.assertEqual(check(text), [])

    def test_paragraph_can_have_six_sentences(self):
        self.assertEqual(check(" ".join(["Remove the cap."] * 6)), [])

    def test_paragraph_with_seven_sentences_is_an_error(self):
        [f] = check(" ".join(["Remove the cap."] * 7))
        self.assertEqual(f.rule, "6.6")

    def test_table_cells_are_checked(self):
        [f] = check("| Valve | Cap |\n|---|---|\n| Frobnicate the valve. | Open it. |\n")
        self.assertEqual((f.rule, f.line), ("1.1", 3))


class PunctuationTest(unittest.TestCase):
    def test_semicolon_is_an_error(self):
        [f] = check("Open the valve; remove the cap.")
        self.assertEqual(f.rule, "8.1")

    def test_contraction_is_an_error(self):
        [f] = check("It isn't open.")
        self.assertEqual(f.rule, "4.2")

    def test_latin_abbreviation_is_an_error(self):
        [f] = check("Remove the valve, e.g. the cap.")
        self.assertEqual(f.rule, "GR-6")


class MarkdownTest(unittest.TestCase):
    def test_code_blocks_inline_code_and_links_are_not_checked(self):
        text = ("Open `frob.py` and [the valve](https://frob.example/frob).\n\n"
                "```\nfrobnicate everything\n```\n")
        self.assertEqual(check(text), [])

    def test_code_block_that_contains_a_fence_is_not_checked(self):
        cases = {
            "longer fence": "````markdown\n```bash\nfrob\n```\nfrob\n````\n",
            "other character": "~~~\n```\nfrob\n~~~\n",
            "fence with an info string": "```\n```bash\nfrob\n```\n",
        }
        for name, fenced in cases.items():
            with self.subTest(name):
                [f] = check(fenced + "\nFrobnicate the valve.\n")
                self.assertIn('"frobnicate"', f.message)

    def test_quoted_text_is_not_checked(self):
        self.assertEqual(check('Open the "Frob Settings" valve.'), [])

    def test_front_matter_is_not_checked(self):
        self.assertEqual(
            check("---\nname: frob\ndescription: Use when frobbing\n---\n\nOpen the valve.\n"),
            [])

    def test_heading_words_are_checked(self):
        [f] = check("# Frob\n\nOpen the valve.\n")
        self.assertEqual((f.rule, f.line), ("1.1", 1))

    def test_line_numbers_follow_the_source(self):
        [f] = check("Open the valve.\n\nOpen the\nfrob.\n")
        self.assertEqual(f.line, 4)


class MainTest(unittest.TestCase):
    def run_main(self, text, *options):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "dictionary.json").write_text(json.dumps(DATA), encoding="utf-8")
            (tmp / "words.md").write_text(WORDS, encoding="utf-8")
            (tmp / "general.md").write_text("", encoding="utf-8")
            (tmp / "text.md").write_text(text, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["--dictionary", str(tmp / "dictionary.json"),
                             "--words", str(tmp / "words.md"),
                             "--general-words", str(tmp / "general.md")]
                            + (list(options) or [str(tmp / "text.md")]))
        return code, out.getvalue()

    def test_lookup_gives_the_status_of_each_word(self):
        code, out = self.run_main("", "--lookup", "flarn", "valve", "Slack", "frob")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertIn("ZORP (v)", lines[0])
        self.assertIn("approved", lines[1])
        self.assertIn("TN", lines[2])
        self.assertIn("not in", lines[3])

    def test_lookup_finds_a_phrase_of_a_word_list_and_of_the_dictionary(self):
        code, out = self.run_main("", "--lookup", "time off", "Comes on")
        self.assertEqual(code, 0)
        time_off, comes_on = out.splitlines()
        self.assertIn("time off (TN, category 9) is in a word list.", time_off)
        self.assertIn("COME ON (v) is approved", comes_on)

    def test_lookup_of_a_hyphenated_word_gives_each_part(self):
        _, out = self.run_main("", "--lookup", "read-only", "read-flarn")
        accepted, rejected = out.splitlines()
        self.assertNotIn("not in the dictionary", accepted)
        self.assertIn("ONLY (adv) is approved", accepted)
        self.assertIn('"read-flarn" is not in the dictionary', rejected)
        self.assertIn("ZORP (v)", rejected)

    def test_lookup_of_a_number_word_tells_that_it_is_a_technical_noun(self):
        _, out = self.run_main("", "--lookup", "two")
        self.assertIn("technical noun", out)
        self.assertNotIn("not in the dictionary", out)

    def test_exit_code_is_0_when_there_are_no_errors(self):
        code, _ = self.run_main("Remove the cap.\n")
        self.assertEqual(code, 0)

    def test_exit_code_is_1_and_the_error_shows_file_and_line(self):
        code, out = self.run_main("Remove the cap.\n\nFrobnicate it.\n")
        self.assertEqual(code, 1)
        self.assertIn("text.md:3:", out)

    def test_file_that_the_checker_cannot_read_gives_exit_code_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.md"
            not_utf8 = Path(tmp) / "not-utf8.md"
            not_utf8.write_bytes(b"\xff Remove the cap.\n")
            for path in (missing, not_utf8):
                with self.subTest(path=path.name):
                    code, out = self.run_main("", str(path))
                    self.assertEqual(code, 2)
                    self.assertIn("cannot read %s" % path, out)



HEADER = "| Word | Type | Category | Forms | Information |\n|---|---|---|---|---|\n"


class WordListsTest(unittest.TestCase):
    def run_lists(self, text, general, user, *options):
        """Do the checker with a general word list and a word list of the user. None: no file."""
        def write(path, content):
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "ste100-dictionary.json").write_text(json.dumps(DATA), encoding="utf-8")
            write(tmp / "general.md", general)
            if user is not None:
                write(tmp / "ste-word-list.md", user)
            (tmp / "text.md").write_text(text, encoding="utf-8")
            return run("--data", str(tmp), "--general-words", str(tmp / "general.md"),
                       *(list(options) or [str(tmp / "text.md")]))

    def test_words_of_the_two_lists_are_permitted(self):
        code, out = self.run_lists("Remove the Slack token.\n", HEADER + "| Slack | TN | 11 | | |\n",
                                   HEADER + "| token | TN | 19 | | |\n")
        self.assertEqual(code, 0, out)

    def test_without_a_word_list_of_the_user_the_checker_uses_the_general_list(self):
        code, out = self.run_lists("Remove the Slack token.\n",
                                   HEADER + "| Slack | TN | 11 | | |\n", None)
        self.assertEqual(code, 1)
        self.assertIn('"token" is not in the dictionary or the word lists.', out)

    def test_word_list_of_the_user_without_a_table_is_permitted(self):
        for user in ("", "# STE Word List of the User\n\nNo words.\n"):
            with self.subTest(user=user):
                code, out = self.run_lists("Remove the Slack cap.\n",
                                           HEADER + "| Slack | TN | 11 | | |\n", user)
                self.assertEqual(code, 0, out)

    def test_only_the_word_list_of_the_user_gives_findings(self):
        code, out = self.run_lists("Remove the cap.\n", HEADER + "| valve | TN | 1 | | |\n",
                                   HEADER + "| trel | TN | 19 | | |\n")
        self.assertEqual(code, 0, out)
        self.assertNotIn("general.md", out)
        self.assertIn("ste-word-list.md:3: REVIEW", out)
        self.assertIn("STE check: 0 errors, 1 items to review.", out)

    def test_word_list_that_is_not_utf8_gives_exit_code_2(self):
        bad = b"\xff" + HEADER.encode()
        for general, user, name in ((bad, HEADER, "general.md"), (HEADER, bad, "ste-word-list.md")):
            with self.subTest(name=name):
                code, out = self.run_lists("Remove the cap.\n", general, user)
                self.assertEqual(code, 2)
                self.assertIn("cannot read", out)
                self.assertIn(name, out)

    def test_word_in_the_two_lists_is_permitted(self):
        row = "| token | TN | 19 | | |\n"
        code, out = self.run_lists("Remove the token.\n", HEADER + row, HEADER + row)
        self.assertEqual(code, 0, out)

    def test_lookup_finds_a_word_of_the_word_list_of_the_user(self):
        code, out = self.run_lists("", HEADER, HEADER + "| token | TN | 19 | | |\n",
                                   "--lookup", "token")
        self.assertEqual(code, 0)
        self.assertIn("token (TN, category 19) is in a word list.", out)

    def test_lookup_gives_each_row_of_a_word_with_two_meanings(self):
        rows = "| subject | TN | 15 | | |\n| subject | TN | 19 | | |\n"
        code, out = self.run_lists("", HEADER, HEADER + rows, "--lookup", "subject")
        self.assertEqual(code, 0)
        self.assertIn("subject (TN, category 15) is in a word list.", out)
        self.assertIn("subject (TN, category 19) is in a word list.", out)

    def test_lookup_gives_a_row_that_is_in_the_two_lists_one_time(self):
        row = "| token | TN | 19 | | |\n"
        _, out = self.run_lists("", HEADER + row, HEADER + row, "--lookup", "token")
        self.assertEqual(out.count("is in a word list"), 1, out)


class GeneralWordListTest(unittest.TestCase):
    def test_forms_column_gives_only_the_forms_that_the_checker_cannot_make(self):
        words = ProjectWords.parse(GENERAL_WORDS.read_text(encoding="utf-8"))
        made = {"TN": plural_forms, "TV": regular_verb_forms}
        redundant = [(e["line"], e["word"], form) for e in words.entries for form in e["forms"]
                     if e["type"] in made and form in made[e["type"]](e["word"].lower())]
        self.assertEqual(redundant, [])


if __name__ == "__main__":
    unittest.main()
