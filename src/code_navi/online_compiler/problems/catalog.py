"""Small server-owned catalog used by the practice submit endpoint."""

from __future__ import annotations

from .models import ProblemDefinition, ProblemVersion, TestCase
from .repository import InMemoryProblemRepository

TEMPERATURE_CONVERT = ProblemVersion(
    "temperature-convert",
    1,
    "python",
    "celsius = float(input())\n\n# TODO: calculate and print Fahrenheit\n",
    (
        TestCase("zero", "0\n", "32.00\n", False),
        TestCase("sample", "25\n", "77.00\n", False),
        TestCase("freezing", "-40\n", "-40.00\n", True, 2),
        TestCase("boiling", "100\n", "212.00\n", True, 2),
    ),
)
LEAP_YEAR = ProblemVersion(
    "leap-year",
    1,
    "python",
    "year = int(input())\n\n# TODO: print LEAP or COMMON\n",
    (
        TestCase("leap", "2024\n", "LEAP\n", False),
        TestCase("common", "2023\n", "COMMON\n", False),
        TestCase("century", "1900\n", "COMMON\n", True, 2),
        TestCase("four-century", "2000\n", "LEAP\n", True, 2),
    ),
)
DIGIT_SUM = ProblemVersion(
    "digit-sum",
    1,
    "python",
    "number = int(input())\n\n# TODO: sum digits using arithmetic\n",
    (
        TestCase("sample", "50231\n", "11\n", False),
        TestCase("zero", "0\n", "0\n", False),
        TestCase("large", "99999\n", "45\n", True, 2),
        TestCase("place-value", "100000\n", "1\n", True, 2),
    ),
)

DEFAULT_PROBLEM_DEFINITIONS = (
    ProblemDefinition(
        "temperature-convert",
        "温度单位换算",
        "将摄氏温度转换为华氏温度并保留两位小数。",
        ("输入输出", "数值"),
        1,
    ),
    ProblemDefinition(
        "leap-year", "闰年判断", "根据公历规则判断年份是否为闰年。", ("分支", "布尔"), 1
    ),
    ProblemDefinition(
        "digit-sum",
        "整数各位求和",
        "使用循环计算非负整数的十进制各位数字之和。",
        ("循环", "整数"),
        1,
    ),
    ProblemDefinition(
        "palindrome",
        "字符串回文判断",
        "判断输入字符串是否从两侧读取都完全一致。",
        ("字符串", "分支"),
        1,
    ),
    ProblemDefinition(
        "list-sum", "整数列表求和", "读取空格分隔的整数并输出总和。", ("列表", "循环"), 1
    ),
    ProblemDefinition(
        "word-frequency", "统计最高频单词", "输出出现次数最多的单词及其次数。", ("字典", "统计"), 1
    ),
    ProblemDefinition(
        "bracket-match", "括号序列校验", "判断括号是否正确闭合并保持嵌套顺序。", ("栈", "算法"), 1
    ),
)
PALINDROME = ProblemVersion(
    "palindrome",
    1,
    "python",
    "text = input().strip()\n\n# TODO\n",
    (
        TestCase("level", "level\n", "YES\n", False),
        TestCase("python", "python\n", "NO\n", False),
        TestCase("empty", "\n", "YES\n", True, 2),
    ),
)
LIST_SUM = ProblemVersion(
    "list-sum",
    1,
    "python",
    "numbers = list(map(int, input().split()))\n\n# TODO\n",
    (
        TestCase("sample", "12 8 -3 5\n", "22\n", False),
        TestCase("single", "7\n", "7\n", False),
        TestCase("hidden", "100 -50 2\n", "52\n", True, 2),
    ),
)
WORD_FREQUENCY = ProblemVersion(
    "word-frequency",
    1,
    "python",
    "words = input().split()\n\n# TODO\n",
    (
        TestCase("sample", "pear apple pear banana apple pear\n", "pear 3\n", False),
        TestCase("tie", "b a b a\n", "a 2\n", True, 2),
    ),
)
BRACKET_MATCH = ProblemVersion(
    "bracket-match",
    1,
    "python",
    "text = input().strip()\n\n# TODO\n",
    (
        TestCase("valid", "{[()]}\n", "VALID\n", False),
        TestCase("invalid", "([)]\n", "INVALID\n", False),
        TestCase("hidden", "(({}[]))\n", "VALID\n", True, 2),
    ),
)
DEFAULT_PROBLEM_VERSIONS = (
    TEMPERATURE_CONVERT,
    LEAP_YEAR,
    DIGIT_SUM,
    PALINDROME,
    LIST_SUM,
    WORD_FREQUENCY,
    BRACKET_MATCH,
)


def build_default_problem_repository() -> InMemoryProblemRepository:
    return InMemoryProblemRepository(DEFAULT_PROBLEM_VERSIONS)
