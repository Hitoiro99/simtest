"""Multiplicative SI units. Unsupported or dimensionally different units fail."""

import ast
import math
from solvers.exceptions import ConfigurationError

# dimensions: mass, length, time, temperature
BASE = {
    "kg": (1, (1, 0, 0, 0)),
    "g": (0.001, (1, 0, 0, 0)),
    "m": (1, (0, 1, 0, 0)),
    "cm": (0.01, (0, 1, 0, 0)),
    "mm": (0.001, (0, 1, 0, 0)),
    "s": (1, (0, 0, 1, 0)),
    "ms": (0.001, (0, 0, 1, 0)),
    "min": (60, (0, 0, 1, 0)),
    "K": (1, (0, 0, 0, 1)),
    "Pa": (1, (1, -1, -2, 0)),
    "kPa": (1000, (1, -1, -2, 0)),
    "bar": (100000, (1, -1, -2, 0)),
    "N": (1, (1, 1, -2, 0)),
    "Hz": (1, (0, 0, -1, 0)),
    "rad": (1, (0, 0, 0, 0)),
}


def parse(unit):
    if unit in (None, "", "1"):
        return 1, (0, 0, 0, 0)
    if not isinstance(unit, str) or len(unit) > 128:
        raise ConfigurationError("非法单位")
    try:
        tree = ast.parse(unit.replace("^", "**"), mode="eval")
    except SyntaxError:
        raise ConfigurationError("单位语法错误: " + unit)

    def visit(n):
        if isinstance(n, ast.Name) and n.id in BASE:
            return BASE[n.id]
        if isinstance(n, ast.Constant) and n.value == 1:
            return 1, (0, 0, 0, 0)
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mult, ast.Div)):
            a, da = visit(n.left)
            b, db = visit(n.right)
            sign = 1 if isinstance(n.op, ast.Mult) else -1
            return a * (b**sign), tuple(x + sign * y for x, y in zip(da, db))
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
            power = n.right
            sign = 1
            if isinstance(power, ast.UnaryOp) and isinstance(power.op, ast.USub):
                sign, power = -1, power.operand
            if not isinstance(power, ast.Constant) or type(power.value) is not int or abs(power.value) > 12:
                raise ConfigurationError("单位指数必须为有限整数")
            a, da = visit(n.left)
            exponent = sign * power.value
            return a**exponent, tuple(x * exponent for x in da)
        raise ConfigurationError("未知或不支持的单位: " + unit)

    return visit(tree.body)


def factor(source, target):
    a, da = parse(source)
    b, db = parse(target)
    if da != db:
        raise ConfigurationError("单位不兼容: %s -> %s" % (source, target))
    return a / b


def convert(value, source, target):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ConfigurationError("数值必须有限")
    return value * factor(source, target)
