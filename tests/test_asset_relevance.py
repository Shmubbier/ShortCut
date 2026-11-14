import unittest

import asset_search


def c(title, page=""):
    return {"title": title, "source_page": page or "https://example.org/x"}


class OnTopicTest(unittest.TestCase):
    def names(self, cands, q):
        return [x["title"] for x in asset_search.on_topic(cands, q)]

    def test_both_words_needed_when_both_common(self):
        got = self.names([c("Kenny Rogers on stage"), c("Kenny Rogers 1980"), c("Sean Kenny NASA engineer")], "kenny rogers")
        self.assertEqual(got, ["Kenny Rogers on stage", "Kenny Rogers 1980"])

    def test_rare_word_not_required(self):
        got = self.names([c("Ube halaya (Philippines)"), c("Ube ice cream"), c("Purple cake")], "why filipinos love ube")
        self.assertEqual(got, ["Ube halaya (Philippines)", "Ube ice cream"])

    def test_off_topic_game_dropped(self):
        got = self.names([c("Mount Everest north face"), c("Everest base camp", "https://x.org/mount-everest"), c("Mount & Blade screenshot")], "mount everest")
        self.assertNotIn("Mount & Blade screenshot", got)
        self.assertEqual(len(got), 2)

    def test_nothing_matches(self):
        self.assertEqual(self.names([c("Cat"), c("Dog")], "jeepney"), [])


if __name__ == "__main__":
    unittest.main()
