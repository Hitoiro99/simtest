"""Bounded arithmetic interpreter; no eval, imports, attributes or indexing."""

import ast
import math
import operator

from solvers.exceptions import ConfigurationError

FUNCTIONS = {name: getattr(math, name) for name in ("sin", "cos", "tan", "exp", "sqrt", "log", "log10", "fabs")}
FUNCTIONS.update(abs=abs, min=min, max=max)
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


def validate_expression(expression, names):
    if not isinstance(expression, str) or len(expression) > 2048:
        raise ConfigurationError("表达式长度或类型非法")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ConfigurationError("表达式语法错误: %s" % exc)
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise ConfigurationError("表达式过于复杂")
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.UAdd,
        ast.USub,
    ) + tuple(OPERATORS)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ConfigurationError("禁止的表达式节点: " + type(node).__name__)
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float) or not math.isfinite(node.value)):
            raise ConfigurationError("表达式常量必须是有限数值")
        if isinstance(node, ast.Name) and node.id not in set(names) | set(FUNCTIONS) | {"pi"}:
            raise ConfigurationError("未知表达式参数: " + node.id)
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in FUNCTIONS
                or node.keywords
                or not 1 <= len(node.args) <= 8
            ):
                raise ConfigurationError("禁止的函数调用")
    return tree


def evaluate(expression, variables):
    tree = validate_expression(expression, variables)

    def visit(node, depth=0):
        if depth > 32:
            raise ConfigurationError("表达式嵌套过深")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "pi":
                return math.pi
            if node.id not in variables:
                raise ConfigurationError("未知表达式参数: " + node.id)
            if type(variables[node.id]) not in (int, float):
                raise ConfigurationError("表达式参数必须为数值")
            return variables[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand, depth + 1)
            return result if isinstance(node.op, ast.UAdd) else -result
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e100):
                raise ConfigurationError("指数运算超出安全范围")
            return OPERATORS[type(node.op)](left, right)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FUNCTIONS
            and not node.keywords
        ):
            if not 1 <= len(node.args) <= 8:
                raise ConfigurationError("函数参数数量非法")
            return FUNCTIONS[node.func.id](*(visit(a, depth + 1) for a in node.args))
        raise ConfigurationError("禁止的表达式节点: " + type(node).__name__)

    try:
        result = float(visit(tree.body))
        if not math.isfinite(result):
            raise ValueError("NaN/Inf")
        return result
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ConfigurationError("表达式求值失败: %s" % exc)
