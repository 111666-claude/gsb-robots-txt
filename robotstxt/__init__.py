"""robots.txt 解析与匹配。"""

from .rules import RobotsError, Rules, allowed, parse

__all__ = ["RobotsError", "Rules", "allowed", "parse"]
