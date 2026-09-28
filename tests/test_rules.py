import unittest

from robotstxt.rules import allowed, parse


def build(text):
    return parse(text)


class ParseTest(unittest.TestCase):
    def test_two_groups(self):
        rules = build("User-agent: a\nDisallow: /x\n\nUser-agent: b\nDisallow: /y\n")
        self.assertEqual(len(rules.groups), 2)
        self.assertEqual(rules.groups[0][0], ["a"])
        self.assertEqual(rules.groups[1][0], ["b"])

    def test_comments_and_blank_lines(self):
        rules = build("# comment\nUser-agent: a\n\nDisallow: /x  # tail\n")
        self.assertEqual(rules.groups[0][1], [("/x", False)])

    def test_sitemaps_are_collected(self):
        rules = build("Sitemap: http://example.com/s.xml\nUser-agent: *\nDisallow:\n")
        self.assertEqual(rules.sitemaps, ["http://example.com/s.xml"])

    def test_crawl_delay_is_collected(self):
        rules = build("User-agent: a\nCrawl-delay: 5\nDisallow: /x\n")
        self.assertEqual(rules.delays.get("a"), "5")


class AllowTest(unittest.TestCase):
    def test_plain_disallow(self):
        rules = build("User-agent: *\nDisallow: /private\n")
        self.assertFalse(allowed(rules, "/private/x", "any"))

    def test_allowed_when_not_matched(self):
        rules = build("User-agent: *\nDisallow: /private\n")
        self.assertTrue(allowed(rules, "/public", "any"))

    def test_empty_disallow_allows_everything(self):
        rules = build("User-agent: *\nDisallow:\n")
        self.assertTrue(allowed(rules, "/anything", "any"))

    def test_specific_agent_is_used(self):
        rules = build("User-agent: googlebot\nDisallow: /only-for-bot\n")
        self.assertFalse(allowed(rules, "/only-for-bot", "Googlebot/2.1"))
        self.assertTrue(allowed(rules, "/only-for-bot", "other"))

    def test_no_rules_allows(self):
        self.assertTrue(allowed(build(""), "/x", "*"))


if __name__ == "__main__":
    unittest.main()
