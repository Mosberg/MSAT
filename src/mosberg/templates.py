import os
from jinja2 import Environment, FileSystemLoader


def render_template(path: str, context: dict | None = None, template_dir: str | None = None) -> str:
    context = context or {}
    template_dir = template_dir or os.path.abspath(os.path.dirname(path) or ".")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(os.path.basename(path))
    return template.render(**context)
