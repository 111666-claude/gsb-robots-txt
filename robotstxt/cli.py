"""命令行入口：判断路径是否被 robots.txt 允许。"""

import argparse
import sys

from .rules import RobotsError, allowed, parse


def build_parser():
    parser = argparse.ArgumentParser(prog="robots-txt", description="robots.txt 解析与匹配")
    parser.add_argument("--rules", help="robots.txt 内容（用 \\n 表示换行）")
    parser.add_argument("--path", default="/", help="要判断的路径")
    parser.add_argument("--ua", default="*", help="User-Agent")
    parser.add_argument("--sitemaps", action="store_true", help="额外打印 Sitemap")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.rules is None:
        print("错误：需要 --rules", file=sys.stderr)
        return 2
    try:
        rules = parse(args.rules.replace("\\n", "\n"))
    except RobotsError as error:
        print("错误：%s" % error, file=sys.stderr)
        return 1
    print("allowed=%s" % ("true" if allowed(rules, args.path, args.ua) else "false"))
    if args.sitemaps:
        for sitemap in rules.sitemaps:
            print("sitemap=%s" % sitemap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
