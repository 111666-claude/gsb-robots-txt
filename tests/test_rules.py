import unittest

from robotstxt.rules import RobotsError, allowed, parse


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


class WildcardTest(unittest.TestCase):
    def test_star_matches_any_sequence(self):
        rules = build("User-agent: *\nDisallow: /*.pdf\n")
        self.assertFalse(allowed(rules, "/a/b.pdf", "any"))
        self.assertFalse(allowed(rules, "/x.pdf/y", "any"))  # 前缀命中即可
        self.assertTrue(allowed(rules, "/a/b.txt", "any"))

    def test_dollar_anchors_end(self):
        rules = build("User-agent: *\nDisallow: /*.pdf$\n")
        self.assertFalse(allowed(rules, "/a/b.pdf", "any"))
        self.assertTrue(allowed(rules, "/a/b.pdfx", "any"))
        self.assertTrue(allowed(rules, "/a/b.pdf/x", "any"))

    def test_dollar_only_special_at_end(self):
        rules = build("User-agent: *\nDisallow: /a$b\n")
        self.assertFalse(allowed(rules, "/a$b/c", "any"))
        self.assertTrue(allowed(rules, "/ab", "any"))

    def test_literal_prefix_match(self):
        rules = build("User-agent: *\nDisallow: /pub\n")
        self.assertFalse(allowed(rules, "/public", "any"))


class LongestMatchTest(unittest.TestCase):
    def test_longer_allow_beats_shorter_disallow(self):
        rules = build("User-agent: *\nDisallow: /pub\nAllow: /pub/x\n")
        self.assertTrue(allowed(rules, "/pub/x", "any"))
        self.assertFalse(allowed(rules, "/pub/y", "any"))


    def test_longer_disallow_beats_shorter_allow(self):
        rules = build("User-agent: *\nAllow: /pub\nDisallow: /pub/x\n")
        self.assertFalse(allowed(rules, "/pub/x", "any"))

    def test_tie_prefers_allow(self):
        rules = build("User-agent: *\nDisallow: /a\nAllow: /a\n")
        self.assertTrue(allowed(rules, "/a/b", "any"))
        rules = build("User-agent: *\nAllow: /a\nDisallow: /a\n")
        self.assertTrue(allowed(rules, "/a/b", "any"))

    def test_length_ignores_dollar(self):
        rules = build("User-agent: *\nDisallow: /abcd$\nAllow: /ab\n")
        self.assertFalse(allowed(rules, "/abcd", "any"))


class GroupSelectionTest(unittest.TestCase):
    TEXT = (
        "User-agent: *\n"
        "Disallow: /star-only\n"
        "User-agent: googlebot\n"
        "Disallow: /bot-only\n"
        "User-agent: bot\n"
        "User-agent: crawl\n"
        "Disallow: /short-only\n"
    )

    def test_longest_agent_wins(self):
        rules = build(self.TEXT)
        self.assertFalse(allowed(rules, "/bot-only", "Googlebot/2.1"))
        self.assertTrue(allowed(rules, "/star-only", "Googlebot/2.1"))
        self.assertTrue(allowed(rules, "/short-only", "Googlebot/2.1"))

    def test_multi_line_agent_group(self):
        rules = build(self.TEXT)
        self.assertFalse(allowed(rules, "/short-only", "my-crawler/1.0"))
        self.assertFalse(allowed(rules, "/short-only", "some-bot/1.0"))

    def test_star_group_is_fallback(self):
        rules = build(self.TEXT)
        self.assertFalse(allowed(rules, "/star-only", "random-agent"))
        self.assertTrue(allowed(rules, "/bot-only", "random-agent"))

    def test_agent_match_is_case_insensitive(self):
        rules = build("User-agent: GoogleBot\nDisallow: /x\n")
        self.assertFalse(allowed(rules, "/x", "googlebot/2.1"))


class ParseErrorTest(unittest.TestCase):
    def test_rule_without_agent_reports_line(self):
        with self.assertRaises(RobotsError) as ctx:
            build("Sitemap: http://e.com/s.xml\nDisallow: /x\n")
        self.assertIn("2", str(ctx.exception))

    def test_rule_after_group_still_ok(self):
        rules = build("User-agent: a\nDisallow: /x\nDisallow: /y\n")
        self.assertEqual(rules.groups[0][1], [("/x", False), ("/y", False)])


class InvariantTest(unittest.TestCase):
    TEXT = (
        "Sitemap: http://e.com/s.xml\n"
        "User-agent: *\nCrawl-delay: 5\nDisallow: /a*\nAllow: /a/b$\n"
        "User-agent: googlebot\nDisallow: /c\n"
    )

    def test_repeated_parse_is_identical(self):
        first = build(self.TEXT)
        second = build(self.TEXT)
        self.assertEqual(first.groups, second.groups)
        self.assertEqual(first.sitemaps, second.sitemaps)
        self.assertEqual(first.delays, second.delays)

    def test_result_depends_only_on_inputs(self):
        rules = build(self.TEXT)
        snapshot = (list(rules.groups), list(rules.sitemaps), dict(rules.delays))
        before = allowed(rules, "/a/b", "googlebot")
        allowed(rules, "/c", "other")
        after = allowed(rules, "/a/b", "googlebot")
        self.assertEqual(before, after)
        self.assertEqual(snapshot, (rules.groups, rules.sitemaps, rules.delays))


def ref_match(pattern, path):
    """参考匹配：* 通配、末尾 $ 锚定、前缀命中，独立实现用于对照。"""
    if not pattern:
        return False
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    if anchored and body == "":
        return path == ""  # 模式只有 $：仅命中空路径
    if anchored and "*" not in body:
        return path == body  # 无通配的锚定模式必须整路径相等
    segments = body.split("*")
    if anchored and segments[-1]:
        tail = segments[-1]
        if not path.endswith(tail):
            return False
        path = path[: len(path) - len(tail)]
        segments = segments[:-1]
    pos = 0
    for i, segment in enumerate(segments):
        if i == 0:
            if not path.startswith(segment):
                return False
            pos = len(segment)
        else:
            found = path.find(segment, pos)
            if found < 0:
                return False
            pos = found + len(segment)
    return True


def ref_allowed(rules, path, user_agent):
    """参考判断：线性扫全部规则，取最长命中 + Allow 优先。"""
    agent = user_agent.lower()
    best_score, best_entries = -1, None
    for agents, entries in rules.groups:
        score = -1
        for token in agents:
            if token == "*":
                score = max(score, 0)
            elif token and token in agent:
                score = max(score, len(token))
        if score > best_score:
            best_score, best_entries = score, entries
    if best_entries is None:
        return True
    best_length, best_allow = -1, True
    for pattern, allow in best_entries:
        if ref_match(pattern, path):
            length = len(pattern[:-1] if pattern.endswith("$") else pattern)
            if length > best_length or (length == best_length and allow):
                best_length, best_allow = length, allow
    return best_allow if best_length >= 0 else True


class DifferentialTest(unittest.TestCase):
    def test_matches_reference_on_random_inputs(self):
        import random

        rng = random.Random(20260928)
        agents_pool = ["*", "googlebot", "bot", "bing", "crawler"]
        uas = ["Googlebot/2.1", "bingbot/2.0", "my-crawler", "other", "*", ""]

        def rand_pattern():
            parts = []
            for _ in range(rng.randint(1, 5)):
                parts.append(rng.choice(["/", "a", "b", ".", "*", "pub", ""]))
            pattern = "".join(parts)
            if rng.random() < 0.3:
                pattern += "$"
            return pattern

        for _ in range(2000):
            lines = []
            for _ in range(rng.randint(1, 3)):
                for _ in range(rng.randint(1, 2)):
                    lines.append("User-agent: " + rng.choice(agents_pool))
                for _ in range(rng.randint(1, 6)):
                    field = rng.choice(["Disallow", "Allow"])
                    lines.append("%s: %s" % (field, rand_pattern()))
            rules = build("\n".join(lines) + "\n")
            path = "/" + "".join(rng.choice("ab/pub.pdf") for _ in range(rng.randint(0, 12)))
            ua = rng.choice(uas)
            self.assertEqual(
                allowed(rules, path, ua),
                ref_allowed(rules, path, ua),
                "rules=%r path=%r ua=%r" % (lines, path, ua),
            )


class PerformanceTest(unittest.TestCase):
    def test_10k_rules_100k_queries_under_one_second(self):
        import random
        import time

        rng = random.Random(7)
        lines = ["User-agent: *"]
        for i in range(10000):
            field = "Allow" if i % 7 == 0 else "Disallow"
            pattern = "/seg%d/%s" % (rng.randint(0, 500), rng.choice(["a", "b*", "c*", "d"]))
            if i % 11 == 0:
                pattern += "$"
            lines.append("%s: %s" % (field, pattern))
        rules = build("\n".join(lines) + "\n")
        paths = ["/seg%d/%s" % (rng.randint(0, 500), rng.choice(["a", "bx", "cy", "dz"])) for _ in range(100000)]
        start = time.perf_counter()
        for path in paths:
            allowed(rules, path, "benchbot/1.0")
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0, "100k 次查询耗时 %.3fs" % elapsed)
