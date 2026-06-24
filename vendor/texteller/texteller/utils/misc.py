from textwrap import dedent


def lines_dedent(s: str) -> str:
    return dedent(s).strip()
