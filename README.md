# robots-txt

robots.txt 解析与匹配（RFC 9309 子集：群组、通配符、最长匹配），只用 Python 标准库。

```
python3 -m robotstxt.cli --rules 'User-agent: *\nDisallow: /pub\nAllow: /pub/x' --path /pub/x
python3 -m robotstxt.cli --rules 'User-agent: *\nDisallow: /*.pdf$' --path /a/b.pdf
python3 -m unittest discover -s tests -v
```

## 口径（README 为准）

- **按最长匹配决定，Allow 优先**：能命中 `/pub/x` 的规则有 `/pub`（长度 4）和 `/pub/x`（长度 6），
  所以 `--rules 'User-agent: *\nDisallow: /pub\nAllow: /pub/x' --path /pub/x` 按口径是 `allowed=true`，
  现在按文件顺序第一条命中的 `/pub` 说了算，给 `allowed=false`。
- **支持 `*` 与 `$`**：`Disallow: /*.pdf$` 要能命中 `/a/b.pdf`（现在按字面前缀比，给 `allowed=true`）；
  `*` 匹配任意字符序列，`$` 只在模式末尾表示结尾。
- **群组要选最长 UA 匹配**：`--ua Googlebot/2.1` 时 `googlebot` 组（长度 9）优先于 `*` 组（长度 1）；
  现在取第一个能匹配的组，所以会先命中 `*` 组。
- 其它：一条 UA 组可以有多行 `User-agent`；空 `Disallow:` 表示全允许；没有匹配规则即允许；
  `Sitemap` 与 `Crawl-delay` 要收集起来（每组的 delay 归到该组）。
- 不变量：同一份 robots.txt 重复解析得到同样的结构；判断结果只取决于解析结果与传入的 UA/路径。
- 规模：1 万条规则、10 万次查询要在 1 秒内完成（把规则预处理成可快速匹配的形式），内存 O(规则数)。

## 现在的行为

- `_matches` 直接 `path.startswith(pattern)`：`*` 与 `$` 都成了普通字符。
- `allowed` 取第一个能匹配的组，组内第一条命中的规则就返回，不看模式长度。
- 没有 `User-agent` 前缀的 `Disallow` 行被静默丢掉。

## 计划新增的能力

```
--rules 内容     robots.txt 全文（用 \n 表示换行）
--path 路径      要判断的路径
--ua 名称        User-Agent
--sitemaps       额外打印 Sitemap
```

## 输出

```
allowed=true
sitemap=http://example.com/s.xml
```

## 目录

```
robotstxt/rules.py   解析与匹配
robotstxt/cli.py     命令行入口
tests/              unittest 用例
```
