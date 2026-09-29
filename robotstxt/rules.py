"""robots.txt 解析与匹配（RFC 9309 子集），只用标准库。

口径：
- 群组：连续的 ``User-agent`` 行属于同一组，遇到下一条规则行即结束该组；
  多个 UA 组命中时取 UA 名最长的组（大小写不敏感、子串匹配，``*`` 组优先级最低）。
- 匹配：在所有命中路径的规则中取模式最长的一条（长度按去掉末尾 ``$`` 后的字符数），
  长度相同时 Allow 优先；没有任何规则命中即允许。
- 通配符：``*`` 匹配任意字符序列，模式末尾的 ``$`` 表示路径结束；
  其余字符按字面比较，模式是路径前缀也算命中。
- 空 ``Disallow:`` 不命中任何路径（即全允许）。
- ``Sitemap`` 全局收集；``Crawl-delay`` 归到所在组（按该组的 UA 名记录）。

查询使用前缀 trie（无通配符段）与 Aho-Corasick 自动机（含 ``*`` 的规则的字面段）
索引，每次查询只访问与路径相关的候选规则，不线性扫描全部规则。
"""


class RobotsError(ValueError):
    """robots.txt 不合法。"""

    def __init__(self, line_no, message):
        full_message = "第 %d 行：%s" % (line_no, message)
        super().__init__(full_message)
        self.message = full_message
        self.line_no = line_no


class _Matcher:
    """一组规则的匹配索引：trie 索引无 ``*`` 规则，AC 索引含 ``*`` 规则的字面段。"""

    __slots__ = ("entries", "root", "always", "ac_goto", "ac_fail",
                 "ac_ids", "ac_closure", "ac_closure_valid", "tick", "stamp")

    def __init__(self, entries):
        # entries: [(pattern, allow, id)]，空模式（全允许）已在上层剔除
        self.entries = entries
        self.root = {}                 # 无 * 规则按 body（去掉 $）建前缀 trie
        self.always = []              # 仅由 * 组成的模式：命中所有路径
        self.ac_goto = []
        self.ac_fail = []
        self.ac_ids = []
        self.ac_closure = []
        self.ac_closure_valid = []
        self.tick = 0
        self.stamp = [None] * len(entries)
        if entries:
            self._build()

    @staticmethod
    def _split(pattern):
        """返回 (segments, anchored, leading_star, trailing_star)。"""
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        return (body.split("*"), anchored,
                body.startswith("*"), body.endswith("*"))

    def _build(self):
        ac_keys = set()
        for pattern, _allow, entry_id in self.entries:
            segments, _anchored, _lead, trail = self._split(pattern)
            if not any(segments):
                # body 全是 *（含空 body，即仅 "$" 之外的情形）：任意路径都命中
                self.always.append(entry_id)
                continue
            if len(segments) == 1:
                node = self.root
                for ch in segments[0]:
                    node = node.setdefault(ch, {})
                node.setdefault("", []).append(entry_id)
            else:
                for segment in segments:
                    if segment:
                        ac_keys.add((segment, entry_id))
        if ac_keys:
            self._build_ac(sorted(ac_keys))

    def _build_ac(self, keys):
        goto = [{}]
        ids = [[]]
        for word, entry_id in keys:
            node = 0
            for ch in word:
                nxt = goto[node].get(ch)
                if nxt is None:
                    nxt = len(goto)
                    goto[node][ch] = nxt
                    goto.append({})
                    ids.append([])
                node = nxt
            if entry_id not in ids[node]:
                ids[node].append(entry_id)
        fail = [0] * len(goto)
        queue = list(goto[0].values())
        head = 0
        while head < len(queue):
            node = queue[head]
            head += 1
            for ch, child in goto[node].items():
                ancestor = fail[node]
                while ancestor and ch not in goto[ancestor]:
                    ancestor = fail[ancestor]
                fallback = goto[ancestor].get(ch, 0)
                fail[child] = 0 if fallback == child else fallback
                queue.append(child)
        self.ac_goto = goto
        self.ac_fail = fail
        self.ac_ids = ids
        self.ac_closure = [None] * len(goto)
        self.ac_closure_valid = [False] * len(goto)

    def _outputs(self, node):
        """AC 状态 node 经 fail 链能到达的全部命中 id（懒缓存）。"""
        if self.ac_closure_valid[node]:
            return self.ac_closure[node]
        result = []
        cur = node
        while cur:
            own = self.ac_ids[cur]
            if own:
                result.extend(own)
            if self.ac_closure_valid[cur]:
                result.extend(self.ac_closure[cur])
                break
            cur = self.ac_fail[cur]
        self.ac_closure[node] = result
        self.ac_closure_valid[node] = True
        return result

    @staticmethod
    def _match(segments, anchored, leading_star, trailing_star, path):
        pos = 0
        for index, segment in enumerate(segments):
            if not segment:
                continue
            if index == 0 and not leading_star:
                if not path.startswith(segment):
                    return False
                pos = len(segment)
            else:
                found = path.find(segment, pos)
                if found < 0:
                    return False
                pos = found + len(segment)
        return (pos == len(path)) if anchored and not trailing_star else True

    def best(self, path):
        """返回 (best_len, allow)；没有任何规则命中返回 None。"""
        stamp, entries = self.stamp, self.entries
        self.tick += 1
        tick = self.tick
        candidates = list(self.always)
        node = self.root
        for ch in path:
            node = node.get(ch)
            if node is None:
                break
            hits = node.get("")
            if hits:
                for entry_id in hits:
                    if stamp[entry_id] != tick:
                        stamp[entry_id] = tick
                        candidates.append(entry_id)
        if self.ac_goto:
            goto, fail, state = self.ac_goto, self.ac_fail, 0
            for ch in path:
                nxt = goto[state].get(ch)
                if nxt is None:
                    ancestor = fail[state]
                    while ancestor and ch not in goto[ancestor]:
                        ancestor = fail[ancestor]
                    state = goto[ancestor].get(ch, 0)
                else:
                    state = nxt
                if self.ac_ids[state] or fail[state]:
                    for entry_id in self._outputs(state):
                        if stamp[entry_id] != tick:
                            stamp[entry_id] = tick
                            candidates.append(entry_id)
        best_len = -1
        best_allow = True
        for entry_id in candidates:
            pattern, allow = entries[entry_id][0], entries[entry_id][1]
            segments, anchored, lead, trail = self._split(pattern)
            if not self._match(segments, anchored, lead, trail, path):
                continue
            length = len(pattern) - (1 if pattern.endswith("$") else 0)
            if length > best_len or (length == best_len and allow):
                best_len, best_allow = length, allow
        if best_len < 0:
            return None
        return best_len, best_allow


class Rules:
    """解析结果。"""

    def __init__(self):
        self.groups = []          # [(agents, [(pattern, allow)])]
        self.sitemaps = []
        self.delays = {}
        self._matchers = []

    def _build_matchers(self):
        self._matchers = []
        for _agents, entries in self.groups:
            indexed = [(pattern, allow, entry_id)
                       for entry_id, (pattern, allow) in enumerate(entries)
                       if pattern != ""]
            self._matchers.append(_Matcher(indexed))


def parse(text):
    """解析 robots.txt。"""
    rules = Rules()
    agents = []
    entries = []
    started = False
    line_no = 0
    for raw_line in text.splitlines():
        line_no += 1
        content = raw_line.split("#", 1)[0].strip()
        if not content or ":" not in content:
            continue
        field, _, value = content.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if started:
                rules.groups.append((agents, entries))
                agents, entries = [], []
            agents.append(value.lower())
        elif field in ("disallow", "allow"):
            if not agents:
                raise RobotsError(line_no, "%s 行必须属于某个 User-agent 组" % field)
            entries.append((value, field == "allow"))
            started = True
        elif field == "crawl-delay":
            if not agents:
                raise RobotsError(line_no, "crawl-delay 行必须属于某个 User-agent 组")
            for name in agents:
                rules.delays[name] = value
            started = True
        elif field == "sitemap":
            rules.sitemaps.append(value)
    if agents:
        rules.groups.append((agents, entries))
    rules._build_matchers()
    return rules


def _agent_score(agents, agent):
    """命中的 UA 名长度；``*`` 组优先级最低（0）；不命中返回 -1。"""
    best = -1
    for name in agents:
        if name == "*":
            score = 0
        elif name and name in agent:
            score = len(name)
        else:
            continue
        if score > best:
            best = score
    return best


def allowed(rules, path, user_agent=""):
    """判断 ``user_agent`` 访问 ``path`` 是否允许。"""
    agent = user_agent.lower()
    best_index = -1
    best_score = -1
    for index, (group_agents, _entries) in enumerate(rules.groups):
        score = _agent_score(group_agents, agent)
        if score > best_score:
            best_score, best_index = score, index
    if best_index < 0:
        return True
    result = rules._matchers[best_index].best(path)
    return True if result is None else result[1]
