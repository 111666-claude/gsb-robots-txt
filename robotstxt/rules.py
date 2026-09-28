"""robots.txt 解析与匹配（RFC 9309 子集），只用标准库。

缺陷：* 与 $ 当普通字符、组内第一条命中的规则就生效（不比最长）、
群组选择取第一个能匹配的而不是最长的 UA。
"""


class RobotsError(ValueError):
    """robots.txt 不合法。缺陷：不带行号。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Rules:
    """解析结果。"""

    def __init__(self):
        self.groups = []          # [(agents, [(pattern, allow)])]
        self.sitemaps = []
        self.delays = {}


def parse(text):
    """解析 robots.txt。缺陷：没有 UA 的规则被静默丢掉，也不校验字段。"""
    rules = Rules()
    agents = []
    entries = []
    seen_rule = False
    for line in text.splitlines():
        content = line.split("#", 1)[0].strip()
        if not content or ":" not in content:
            continue
        field, _, value = content.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if seen_rule:
                rules.groups.append((agents, entries))
                agents, entries, seen_rule = [], [], False
            agents.append(value.lower())
        elif field in ("disallow", "allow"):
            if not agents:
                continue  # 缺陷：没有 UA 的规则直接丢掉
            entries.append((value, field == "allow"))
            seen_rule = True
        elif field == "sitemap":
            rules.sitemaps.append(value)
        elif field == "crawl-delay":
            rules.delays[agents[-1] if agents else "*"] = value
    if agents:
        rules.groups.append((agents, entries))
    return rules


def _matches(pattern, path):
    """缺陷：* 与 $ 都当普通字符，只做前缀比较。"""
    if pattern == "":
        return False
    return path.startswith(pattern)


def _agent_match(agents, agent):
    for name in agents:
        if name == "*" or name in agent:
            return True
    return False


def allowed(rules, path, user_agent=""):
    """判断路径是否允许。缺陷：第一个能匹配的组就定性，组内第一条命中的规则说了算。"""
    agent = user_agent.lower()
    for agents, entries in rules.groups:
        if not _agent_match(agents, agent):
            continue
        for pattern, allow in entries:
            if _matches(pattern, path):
                return allow
        return True
    return True
