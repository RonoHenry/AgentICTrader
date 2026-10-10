"""The `where` filter and label expressions: a small whitelist over named columns.

A hypothesis narrows its event with ``where``, an expression over feature
columns, and states a rate measure's condition as an expression over label
columns (Requirement 9.3). Both are parsed with ``ast`` and only these are
accepted:

- column names, from the allowed set the caller passes;
- constants (numbers, strings, True/False), and lists or tuples of them;
- comparisons (``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``, chains such as
  ``1 < x <= 3``), ``in`` and ``not in``;
- ``and``, ``or``, ``not``; a bare boolean column (``in_window``).

Anything else (calls, attributes, subscripts, arithmetic, lambdas) is refused,
naming the offending node; so is any column outside the allowed set. The
expression is then evaluated over a DataFrame by this module, never by eval().

A row where any column the expression reads is null is skipped and counted,
never guessed (Req 2.4): ``evaluate`` returns that row as null, not as False.

    f = compile_filter("w1_trend == 'UP' and in_window", feature_columns)
    mask, null = f.evaluate(features)

Validates: Requirements 9.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Collection, Mapping, Optional

import numpy as np
import pandas as pd

__all__ = ["Filter", "FilterError", "compile_filter"]

_COMPARE = {ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "le", ast.Gt: "gt", ast.GtE: "ge",
            ast.In: "in", ast.NotIn: "not in"}


class FilterError(ValueError):
    """An expression outside the whitelist, or naming a column it may not read."""


@dataclass(frozen=True)
class Filter:
    expression: str
    tree: Optional[ast.Expression]
    columns: frozenset[str] = field(default_factory=frozenset)

    def evaluate(self, rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """(mask, null): the rows the expression selects, and the rows skipped
        because a column it reads is null there. They never overlap."""
        if self.tree is None:
            return np.ones(len(rows), dtype=bool), np.zeros(len(rows), dtype=bool)
        null = np.zeros(len(rows), dtype=bool)
        for name in self.columns:
            null |= rows[name].isna().to_numpy()
        value = _evaluate(self.tree.body, rows)
        mask = _as_mask(value, rows, self.expression)
        return mask & ~null, null


def compile_filter(expression: str, columns: Collection[str],
                   forbidden: Optional[Mapping[str, str]] = None) -> Filter:
    """Parse ``expression`` over ``columns``; ``forbidden`` maps a column name to
    why it may not be read here (e.g. "a label column"), for a clearer error."""
    expression = (expression or "").strip()
    if not expression:
        return Filter("", None)
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FilterError(f"{expression!r}: syntax error ({exc.msg})") from None
    names: set[str] = set()
    _check(tree.body, set(columns), forbidden or {}, names, expression)
    return Filter(expression, tree, frozenset(names))


def _check(node: ast.AST, columns: set[str], forbidden: Mapping[str, str], names: set[str], text: str) -> None:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        for value in node.values:
            _check(value, columns, forbidden, names, text)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        _check(node.operand, columns, forbidden, names, text)
    elif isinstance(node, ast.Compare):
        if not all(type(op) in _COMPARE for op in node.ops):
            raise FilterError(f"{text!r}: comparison {type(node.ops[0]).__name__} is not allowed")
        for operand, op in zip(node.comparators, node.ops):
            if isinstance(op, (ast.In, ast.NotIn)) and not isinstance(operand, (ast.List, ast.Tuple)):
                raise FilterError(f"{text!r}: 'in' needs a list of constants, e.g. x in [1, 2]")
        for operand in (node.left, *node.comparators):
            _check_operand(operand, columns, forbidden, names, text)
    elif isinstance(node, ast.Name):
        _name(node, columns, forbidden, names, text)
    else:
        raise FilterError(f"{text!r}: {type(node).__name__} is not allowed; use comparisons, in, and, or, not")


def _check_operand(node: ast.AST, columns: set[str], forbidden: Mapping[str, str], names: set[str], text: str) -> None:
    if isinstance(node, ast.Name):
        _name(node, columns, forbidden, names, text)
    elif _constant(node) is not _NOT_CONSTANT:
        return
    elif isinstance(node, (ast.List, ast.Tuple)):
        for item in node.elts:
            if _constant(item) is _NOT_CONSTANT:
                raise FilterError(f"{text!r}: lists may hold constants only, not {type(item).__name__}")
    else:
        raise FilterError(f"{text!r}: {type(node).__name__} is not allowed; use comparisons, in, and, or, not")


def _name(node: ast.Name, columns: set[str], forbidden: Mapping[str, str], names: set[str], text: str) -> None:
    if node.id in forbidden:
        raise FilterError(f"{text!r}: {node.id} is {forbidden[node.id]} and can't be read here")
    if node.id not in columns:
        raise FilterError(f"{text!r}: unknown column {node.id}")
    names.add(node.id)


_NOT_CONSTANT = object()


def _constant(node: ast.AST) -> Any:
    """The value of a constant (negative numbers included), else _NOT_CONSTANT."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool)):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd))
            and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float))
            and not isinstance(node.operand.value, bool)):
        return -node.operand.value if isinstance(node.op, ast.USub) else node.operand.value
    return _NOT_CONSTANT


def _evaluate(node: ast.AST, rows: pd.DataFrame) -> Any:
    if isinstance(node, ast.BoolOp):
        masks = [_as_mask(_evaluate(v, rows), rows, "") for v in node.values]
        out = masks[0]
        for mask in masks[1:]:
            out = (out & mask) if isinstance(node.op, ast.And) else (out | mask)
        return out
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return ~_as_mask(_evaluate(node.operand, rows), rows, "")
    if isinstance(node, ast.Compare):
        out = np.ones(len(rows), dtype=bool)
        left = _value(node.left, rows)
        for op, comparator in zip(node.ops, node.comparators):
            right = _value(comparator, rows)
            out &= _compare(_COMPARE[type(op)], left, right)
            left = right
        return out
    return _value(node, rows)


def _value(node: ast.AST, rows: pd.DataFrame) -> Any:
    if isinstance(node, ast.Name):
        return rows[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_constant(item) for item in node.elts]
    return _constant(node)


def _compare(op: str, left: Any, right: Any) -> np.ndarray:
    if op in ("in", "not in"):
        hit = pd.Series(left).isin(right).to_numpy()
        return hit if op == "in" else ~hit
    result = {"eq": lambda: left == right, "ne": lambda: left != right, "lt": lambda: left < right,
              "le": lambda: left <= right, "gt": lambda: left > right, "ge": lambda: left >= right}[op]()
    return _bools(result)


def _bools(value: Any) -> np.ndarray:
    if isinstance(value, pd.Series):
        if str(value.dtype) == "boolean":
            return value.fillna(False).to_numpy(dtype=bool)
        if value.dtype == object:
            return value.map(lambda v: bool(v) if v is not None and v is not pd.NA and v == v else False).to_numpy(
                dtype=bool)
        return value.to_numpy(dtype=bool)
    return np.asarray(value, dtype=bool)


def _as_mask(value: Any, rows: pd.DataFrame, text: str) -> np.ndarray:
    if isinstance(value, np.ndarray) and value.dtype == bool:
        return value
    if isinstance(value, pd.Series):
        if value.dtype == bool or str(value.dtype) == "boolean":
            return value.fillna(False).astype(bool).to_numpy()
        if value.dtype == object and value.dropna().map(lambda v: isinstance(v, (bool, np.bool_))).all():
            return value.astype("boolean").fillna(False).to_numpy(dtype=bool)    # None: null, counted apart
        raise FilterError(f"{text!r}: column {value.name} is not true/false; compare it with a value")
    if isinstance(value, bool):
        return np.full(len(rows), value)
    raise FilterError(f"{text!r}: the expression is not a condition")
