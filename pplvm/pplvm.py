#!/usr/bin/env python3
"""pplvm: clean-room interpreter for a subset of HP PPL. Zero dependencies.

Spec sources: HP's published PPL docs + black-box behavior of the virtual calculator.
Supported: numbers, strings, lists, LOCAL, :=, IF/FOR/WHILE/REPEAT, RETURN, EXPORT/functions, PRINT.
Unsupported (raises PPLError): matrices, CAS, graphics, apps, INPUT/CHOOSE, number-format modes.
"""
import math
import re
import sys

KEYWORDS = {"EXPORT", "BEGIN", "END", "LOCAL", "IF", "THEN", "ELSE", "FOR", "FROM", "TO",
            "STEP", "DO", "WHILE", "REPEAT", "UNTIL", "RETURN", "AND", "OR", "NOT"}

TOKEN_RE = re.compile(r"""
    (?P<ws>\s+|//[^\n]*)
  | (?P<num>\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)
  | (?P<str>"[^"]*")
  | (?P<id>[^\W\d]\w*)
  | (?P<op>:=|==|<>|≠|<=|>=|≤|≥|[-+*/^(){}\[\],;<>=])
""", re.X)


class PPLError(Exception):
    pass


class Return(Exception):
    def __init__(self, value):
        self.value = value


def tokenize(src):
    pos, out = 0, []
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise PPLError(f"unexpected character {src[pos]!r} at offset {pos}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        text = m.group()
        if kind == "num":
            out.append(("num", float(text) if re.search(r"[.eE]", text) else int(text)))
        elif kind == "str":
            out.append(("str", text[1:-1]))
        elif kind == "id" and text in KEYWORDS:
            out.append(("kw", text))
        else:
            out.append((kind, text))
    out.append(("eof", None))
    return out


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def at(self, kind, text=None):
        k, v = self.peek()
        return k == kind and (text is None or v == text)

    def accept(self, kind, text=None):
        if self.at(kind, text):
            return self.next()
        return None

    def expect(self, kind, text=None):
        if not self.at(kind, text):
            raise PPLError(f"expected {text or kind}, got {self.peek()[1]!r}")
        return self.next()

    def program(self):
        funcs, stmts = {}, []
        while not self.at("eof"):
            self.accept("kw", "EXPORT")
            if self.at("id") and self.t[self.i + 1] == ("op", "(") and self._is_funcdef():
                name, params, body = self.funcdef()
                funcs[name] = (params, body)
            else:
                stmts.append(self.stmt())
        return funcs, stmts

    def _is_funcdef(self):
        depth, j = 0, self.i + 1
        while True:
            k, v = self.t[j]
            if (k, v) == ("op", "("):
                depth += 1
            elif (k, v) == ("op", ")"):
                depth -= 1
                if depth == 0:
                    return self.t[j + 1] == ("kw", "BEGIN")
            elif k == "eof":
                return False
            j += 1

    def funcdef(self):
        name = self.expect("id")[1]
        self.expect("op", "(")
        params = []
        if not self.at("op", ")"):
            params.append(self.expect("id")[1])
            while self.accept("op", ","):
                params.append(self.expect("id")[1])
        self.expect("op", ")")
        self.expect("kw", "BEGIN")
        body = self.block({"END"})
        self.expect("kw", "END")
        self.expect("op", ";")
        return name, params, body

    def block(self, enders):
        stmts = []
        while not (self.peek()[0] == "kw" and self.peek()[1] in enders) and not self.at("eof"):
            stmts.append(self.stmt())
        return stmts

    def stmt(self):
        if self.accept("kw", "LOCAL"):
            decls = []
            while True:
                n = self.expect("id")[1]
                init = self.expr() if self.accept("op", ":=") else None
                decls.append((n, init))
                if not self.accept("op", ","):
                    break
            self.expect("op", ";")
            return ("local", decls)
        if self.accept("kw", "IF"):
            cond = self.expr()
            self.expect("kw", "THEN")
            then = self.block({"ELSE", "END"})
            els = self.block({"END"}) if self.accept("kw", "ELSE") else []
            self.expect("kw", "END")
            self.expect("op", ";")
            return ("if", cond, then, els)
        if self.accept("kw", "FOR"):
            var = self.expect("id")[1]
            self.expect("kw", "FROM")
            lo = self.expr()
            self.expect("kw", "TO")
            hi = self.expr()
            step = self.expr() if self.accept("kw", "STEP") else ("num", 1)
            self.expect("kw", "DO")
            body = self.block({"END"})
            self.expect("kw", "END")
            self.expect("op", ";")
            return ("for", var, lo, hi, step, body)
        if self.accept("kw", "WHILE"):
            cond = self.expr()
            self.expect("kw", "DO")
            body = self.block({"END"})
            self.expect("kw", "END")
            self.expect("op", ";")
            return ("while", cond, body)
        if self.accept("kw", "REPEAT"):
            body = self.block({"UNTIL"})
            self.expect("kw", "UNTIL")
            cond = self.expr()
            self.expect("op", ";")
            return ("repeat", body, cond)
        if self.accept("kw", "RETURN"):
            e = self.expr()
            self.expect("op", ";")
            return ("return", e)
        e = self.expr()
        if self.accept("op", ":="):
            if e[0] == "call":  # L(2):=x parses as a call; it is an index target
                e = ("index", e[1], e[2])
            if e[0] not in ("var", "index"):
                raise PPLError("invalid assignment target")
            rhs = self.expr()
            self.expect("op", ";")
            return ("assign", e, rhs)
        self.expect("op", ";")
        return ("expr", e)

    # precedence: OR < AND < NOT < comparison < +- < */ < unary - < ^ < postfix
    def expr(self):
        return self.or_()

    def or_(self):
        e = self.and_()
        while self.accept("kw", "OR"):
            e = ("bin", "OR", e, self.and_())
        return e

    def and_(self):
        e = self.not_()
        while self.accept("kw", "AND"):
            e = ("bin", "AND", e, self.not_())
        return e

    def not_(self):
        if self.accept("kw", "NOT"):
            return ("not", self.not_())
        return self.cmp()

    def cmp(self):
        e = self.add()
        k, v = self.peek()
        if k == "op" and v in ("==", "=", "<>", "≠", "<", ">", "<=", "≤", ">=", "≥"):
            self.next()
            e = ("bin", v, e, self.add())
        return e

    def add(self):
        e = self.mul()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.next()[1]
            e = ("bin", op, e, self.mul())
        return e

    def mul(self):
        e = self.unary()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.next()[1]
            e = ("bin", op, e, self.unary())
        return e

    def unary(self):
        if self.accept("op", "-"):
            return ("neg", self.unary())
        return self.pow()

    def pow(self):
        e = self.postfix()
        if self.accept("op", "^"):
            return ("bin", "^", e, self.unary())  # right-assoc
        return e

    def postfix(self):
        e = self.primary()
        while True:
            if self.accept("op", "("):
                args = self.args(")")
                e = ("call", e, args) if e[0] == "var" else ("index", e, args)
            elif self.accept("op", "["):
                e = ("index", e, self.args("]"))
            else:
                return e

    def args(self, close):
        args = []
        if not self.at("op", close):
            args.append(self.expr())
            while self.accept("op", ","):
                args.append(self.expr())
        self.expect("op", close)
        return args

    def primary(self):
        k, v = self.next()
        if k == "num":
            return ("num", v)
        if k == "str":
            return ("str", v)
        if k == "id":
            return ("var", v)
        if (k, v) == ("op", "("):
            e = self.expr()
            self.expect("op", ")")
            return e
        if (k, v) == ("op", "{"):
            return ("list", self.args("}"))
        raise PPLError(f"unexpected token {v!r}")


def fmt(v):
    """Provisional number/list formatting. TODO: verify against virtual calculator."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return "%.12g" % v
    if isinstance(v, list):
        return "{" + ",".join(fmt(x) for x in v) + "}"
    return str(v)


def _num(x):
    if isinstance(x, (int, float)):
        return x
    raise PPLError(f"expected number, got {x!r}")


class Interp:
    def __init__(self, out=None):
        self.out = out or sys.stdout
        self.funcs, self.globals = {}, {}
        self.builtins = {
            "PRINT": lambda *a: self.out.write("".join(fmt(x) for x in a) + "\n"),
            "SIZE": lambda x: len(x),
            "ABS": lambda x: abs(_num(x)),
            "SQRT": lambda x: math.sqrt(_num(x)),
            "FLOOR": lambda x: math.floor(_num(x)),
            "CEILING": lambda x: math.ceil(_num(x)),
            "MAX": lambda *a: max(a[0]) if len(a) == 1 and isinstance(a[0], list) else max(a),
            "MIN": lambda *a: min(a[0]) if len(a) == 1 and isinstance(a[0], list) else min(a),
            "MOD": lambda a, b: a - b * math.floor(a / b),
            "ΣLIST": lambda L: sum(L),
        }

    def run(self, src):
        funcs, stmts = Parser(tokenize(src)).program()
        self.funcs.update(funcs)
        self.exec_block(stmts, self.globals)

    def exec_block(self, stmts, env):
        for s in stmts:
            self.exec(s, env)

    def exec(self, s, env):
        op = s[0]
        if op == "local":
            for name, init in s[1]:
                env[name] = self.eval(init, env) if init else 0
        elif op == "assign":
            val = self.eval(s[2], env)
            tgt = s[1]
            if tgt[0] == "var":
                env[tgt[1]] = val
            else:
                lst = self.eval(tgt[1], env)
                idx = [self.eval(a, env) for a in tgt[2]]
                if not isinstance(lst, list) or len(idx) != 1:
                    raise PPLError("only 1-D list element assignment is supported")
                lst[self._i(lst, idx[0])] = val
        elif op == "expr":
            self.eval(s[1], env)
        elif op == "if":
            self.exec_block(s[2] if self.eval(s[1], env) else s[3], env)
        elif op == "for":
            _, var, lo, hi, step, body = s
            i, hi_v, st = self.eval(lo, env), self.eval(hi, env), self.eval(step, env)
            if st == 0:
                raise PPLError("FOR step is zero")
            while (i <= hi_v) if st > 0 else (i >= hi_v):
                env[var] = i
                self.exec_block(body, env)
                i += st
        elif op == "while":
            while self.eval(s[1], env):
                self.exec_block(s[2], env)
        elif op == "repeat":
            while True:
                self.exec_block(s[1], env)
                if self.eval(s[2], env):
                    break
        elif op == "return":
            raise Return(self.eval(s[1], env))

    @staticmethod
    def _i(lst, idx):
        if not isinstance(idx, int) or not 1 <= idx <= len(lst):
            raise PPLError(f"index {idx!r} out of range 1..{len(lst)}")
        return idx - 1  # PPL lists are 1-based

    def eval(self, e, env):
        k = e[0]
        if k in ("num", "str"):
            return e[1]
        if k == "var":
            name = e[1]
            if name in env:
                return env[name]
            if name in self.globals:
                return self.globals[name]
            raise PPLError(f"undefined variable {name}")
        if k == "list":
            return [self.eval(x, env) for x in e[1]]
        if k == "neg":
            return -_num(self.eval(e[1], env))
        if k == "not":
            return 0 if self.eval(e[1], env) else 1
        if k == "index":
            base = self.eval(e[1], env)
            idx = [self.eval(a, env) for a in e[2]]
            if not isinstance(base, list) or len(idx) != 1:
                raise PPLError("only 1-D list indexing is supported")
            return base[self._i(base, idx[0])]
        if k == "call":
            name = e[1][1]
            args = [self.eval(a, env) for a in e[2]]
            if name in env and isinstance(env[name], list):
                return env[name][self._i(env[name], args[0])]
            if name in self.funcs:
                params, body = self.funcs[name]
                if len(args) != len(params):
                    raise PPLError(f"{name} expects {len(params)} args, got {len(args)}")
                local = dict(zip(params, args))
                try:
                    self.exec_block(body, local)
                except Return as r:
                    return r.value
                return 0
            if name in self.builtins:
                return self.builtins[name](*args)
            raise PPLError(f"unknown function {name}")
        if k == "bin":
            op = e[1]
            if op == "AND":
                return 1 if self.eval(e[2], env) and self.eval(e[3], env) else 0
            if op == "OR":
                return 1 if self.eval(e[2], env) or self.eval(e[3], env) else 0
            a, b = self.eval(e[2], env), self.eval(e[3], env)
            if op == "+":
                if isinstance(a, list) and isinstance(b, list):
                    return a + b  # provisional: PPL concatenates lists with ","; verify
                return _num(a) + _num(b)
            if op == "-":
                return _num(a) - _num(b)
            if op == "*":
                return _num(a) * _num(b)
            if op == "/":
                if _num(b) == 0:
                    raise PPLError("division by zero")  # TODO: PPL returns inf/undef; verify
                q = a / b
                return int(q) if isinstance(a, int) and isinstance(b, int) and a % b == 0 else q
            if op == "^":
                return _num(a) ** _num(b)
            if op in ("==", "="):
                return 1 if a == b else 0
            if op in ("<>", "≠"):
                return 1 if a != b else 0
            if op == "<":
                return 1 if a < b else 0
            if op == ">":
                return 1 if a > b else 0
            if op in ("<=", "≤"):
                return 1 if a <= b else 0
            if op in (">=", "≥"):
                return 1 if a >= b else 0
        raise PPLError(f"cannot evaluate {k}")


def main(argv):
    if len(argv) != 3 or argv[1] != "run":
        print("usage: pplvm.py run FILE.ppl", file=sys.stderr)
        return 2
    try:
        with open(argv[2], encoding="utf-8") as f:
            Interp().run(f.read())
    except PPLError as err:
        print(f"PPL error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
