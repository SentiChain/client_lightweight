"""Keep README examples syntactically valid and aligned with the public client."""

import ast
import re
from pathlib import Path

from sentichain import Client


def test_python_examples_compile():
    readme = Path(__file__).resolve().parents[1] / "README.md"
    snippets = re.findall(r"```python\n(.*?)```", readme.read_text(), re.DOTALL)
    assert snippets
    for snippet in snippets:
        tree = ast.parse(snippet)
        compile(tree, str(readme), "exec")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "client"
            ):
                assert callable(getattr(Client, node.func.attr))
