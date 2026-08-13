from __future__ import annotations

from code_navi.online_compiler.problem_imports import analyze_problem_text


def test_problem_import_preserves_multiline_sample_input_and_output() -> None:
    problems = analyze_problem_text(
        """
题目：矩阵行和
描述：读取一个矩阵，输出每一行的和。
输入：第一行包含 n 和 m，后续 n 行包含整数。
输出：每行一个整数。
样例输入：
2 3
1 2 3
4 5 6
样例输出：
6
15
"""
    )

    assert len(problems) == 1
    assert problems[0].sample_tests[0].stdin == "2 3\n1 2 3\n4 5 6"
    assert problems[0].sample_tests[0].expected_output == "6\n15"


def test_problem_import_reads_sample_block_with_input_and_output_sections() -> None:
    problems = analyze_problem_text(
        """
题目：回文判断
描述：判断输入字符串是否为回文。
输入：一行字符串。
输出：YES 或 NO。
样例：
输入
level
输出
YES
"""
    )

    assert len(problems) == 1
    assert problems[0].sample_tests[0].stdin == "level"
    assert problems[0].sample_tests[0].expected_output == "YES"


def test_problem_import_ignores_invalid_structured_json_instead_of_plaintext_fallback() -> None:
    problems = analyze_problem_text("{bad json", filename="problems.json")

    assert problems == []
