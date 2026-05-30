import tempfile
from mosberg.templates import render_template


def test_render_template_tmpfile():
    content = "Hello {{ name }}"
    with tempfile.TemporaryDirectory() as td:
        path = td + "/greeting.j2"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        out = render_template(path, {"name": "World"})
        assert "Hello World" in out
