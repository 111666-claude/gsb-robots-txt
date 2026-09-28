"""robots.txt 解析与匹配（RFC 9309 子集），只用标准库。

口径：
- 所有能命中路径的规则里取模式最长的一条（长度按去掉末尾 $ 后的字符数算），
  长度相同时 Allow 优先；没有任何规则命中就是允许。
- 支持 *（任意字符序列）与末尾 $（路径结束），其余字符按字面比较；
  模式是路径前缀也算命中。
- 一条 UA 组可以有多行 User-agent；多个 UA 命中时取最长 UA 所属组
  （大小写不敏感、按子串匹配，* 组优先级最低）。
- 空 Disallow: 不命中任何路径（即全允许）；没有 UA 的规则行报错并给行号。
"""

import re


class RobotsError(ValueError):
    """robots.txt 不合法，message 里带行号。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class _GroupIndex:
    """单组规则的匹配索引，避免每次查询线性扫全部规则。

    - literal：无通配符、无 $ 的模式 -> (长度, allow)，按路径前缀查。
    - anchored：无通配符、带 $ 的模式（已去掉 $）-> (长度, allow)，整路径查。
    - wild：含 * 的模式，按首个字面段分组 -> [(长度, allow, 正则)]。
    """

    __slots__ = ("literal", "anchored", "wild")

    def __init__(self):
        self.literal = {}
        self.anchored = {}
        self.wild = {}


class Rules:
    """解析结果。"""

    def __init__(self):
        self.groups = []          # [(agents, [(pattern, allow)])]
        self.sitemaps = []
        self.delays = {}
        self._indexes = []        # 与 groups 一一对应的 _GroupIndex
        self._ua_cache = {}       # ua -> 选中的组下标（-1 表示无命中）


def parse(text):
    """解析 robots.txt；没有 User-agent 的规则行抛 RobotsError（带行号）。"""
    rules = Rules()
    agents = []
    entries = []
    seen_rule = False
    for lineno, line in enumerate(text.splitlines(), 1):
        content = line.split("#", 1)[0].strip()
        if not content or ":" not in content:
            continue
        field, _, value = content.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if seen_rule:
                _close_group(rules, agents, entries)
                agents, entries, seen_rule = [], [], False
            agents.append(value.lower())
        elif field in ("disallow", "allow"):
            if not agents:
                raise RobotsError("第 %d 行：%s 规则前缺少 User-agent" % (lineno, field))
            entries.append((value, field == "allow"))
            seen_rule = True
        elif field == "sitemap":
            rules.sitemaps.append(value)
        elif field == "crawl-delay":
            for agent in agents or ["*"]:
                rules.delays[agent] = value
    if agents:
        _close_group(rules, agents, entries)
    return rules


def _close_group(rules, agents, entries):
    rules.groups.append((agents, entries))
    rules._indexes.append(_build_index(entries))


def _build_index(entries):
    index = _GroupIndex()
    for pattern, allow in entries:
        if not pattern:
            continue  # 空 Disallow:/Allow: 不命中任何路径
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        length = len(body)
        if "*" not in body:
            table = index.anchored if anchored else index.literal
            old = table.get(body)
            if old is None or (allow and not old[1]):
                table[body] = (length, allow)
        else:
            first = body.split("*", 1)[0]
            index.wild.setdefault(first, []).append((length, allow, _compile(body, anchored)))
    return index


def _compile(body, anchored):
    source = ".*".join(re.escape(segment) for segment in body.split("*"))
    if anchored:
        source += r"\Z"
    return re.compile(source)


def _select_group(rules, agent):
    """多个 UA 命中时取最长 UA 所属组；* 优先级最低；并列取先出现的组。"""
    best_score = -1
    best_index = -1
    for i, (agents, _entries) in enumerate(rules.groups):
        score = -1
        for token in agents:
            if token == "*":
                if score < 0:
                    score = 0
            elif token and token in agent:
                if len(token) > score:
                    score = len(token)
        if score > best_score:
            best_score = score
            best_index = i
    return best_index


def _query(index, path):
    """在单组索引里找最长命中；长度相同 Allow 优先；无命中即允许。"""
    best_length = -1
    best_allow = False
    literal = index.literal
    wild = index.wild
    for i in range(len(path) + 1):
        prefix = path[:i]
        if i:
            hit = literal.get(prefix)
            if hit is not None:
                length, allow = hit
                if length > best_length or (length == best_length and allow):
                    best_length, best_allow = length, allow
        candidates = wild.get(prefix)
        if candidates:
            for length, allow, regex in candidates:
                if length < best_length or (length == best_length and best_allow):
                    continue
                if regex.match(path):
                    best_length, best_allow = length, allow
    hit = index.anchored.get(path)
    if hit is not None:
        length, allow = hit
        if length > best_length or (length == best_length and allow):
            best_length, best_allow = length, allow
    return best_allow if best_length >= 0 else True


def allowed(rules, path, user_agent=""):
    """判断路径是否允许：先选最长 UA 命中组，再在组内取最长命中规则。"""
    agent = user_agent.lower()
    group_index = rules._ua_cache.get(agent)
    if group_index is None:
        group_index = _select_group(rules, agent)
        rules._ua_cache[agent] = group_index
    if group_index < 0:
        return True
    return _query(rules._indexes[group_index], path)
