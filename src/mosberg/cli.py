from __future__ import annotations

import click
import yaml

from .inventory import Inventory
from .tasks import run_command
from .templates import render_template


@click.group()
def main():
    """Mosberg Server Automation Toolkit"""


@main.command("list")
@click.option("--inventory", "-i", default="examples/inventory.yml", help="Path to inventory YAML")
def list_hosts(inventory):
    inv = Inventory.from_yaml(inventory)
    for host in inv.hosts:
        click.echo(f"{host.get('name','')} {host.get('host')}")


@main.command("run")
@click.argument("command", nargs=-1)
@click.option("--inventory", "-i", default="examples/inventory.yml")
def run(command, inventory):
    if not command:
        raise click.UsageError("No command provided")
    command = " ".join(command)
    inv = Inventory.from_yaml(inventory)
    results = run_command(inv, command)
    for host, res in results.items():
        click.echo(f"--- {host} ---")
        click.echo(res.get("stdout", ""))
        if res.get("stderr"):
            click.echo("stderr:")
            click.echo(res.get("stderr"))


@main.command("render")
@click.argument("template")
@click.argument("dest")
@click.option("--context-file", "-c", default=None)
def render(template, dest, context_file):
    ctx = {}
    if context_file:
        with open(context_file, "r", encoding="utf-8") as f:
            ctx = yaml.safe_load(f) or {}
    out = render_template(template, ctx)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    click.echo(f"Rendered {template} -> {dest}")


if __name__ == "__main__":
    main()
