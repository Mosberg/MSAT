from __future__ import annotations

import click
import yaml

from .inventory import Inventory
from .tasks import deploy_file, run_command, run_playbook
from .templates import render_template


@click.group()
def main():
    """Mosberg Server Automation Toolkit"""


@main.command("list")
@click.option(
    "--inventory", "-i", default="examples/inventory.yml", help="Path to inventory YAML"
)
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
@click.option("--inventory", "-I", default=None, help="Inventory YAML (for host vars)")
@click.option("--host", "-H", default=None, help="Host name or address to use for vars")
def render(template, dest, context_file, inventory, host):
    ctx = {}
    if context_file:
        with open(context_file, "r", encoding="utf-8") as f:
            ctx = yaml.safe_load(f) or {}
    if inventory and host:
        inv = Inventory.from_yaml(inventory)
        host_obj = None
        for h in inv.hosts:
            if h.get("name") == host or h.get("host") == host:
                host_obj = h
                break
        if host_obj is None:
            raise click.UsageError(f"Host {host} not found in inventory")
        host_vars = host_obj.get("vars") or {}
        ctx.update(host_vars)
    out = render_template(template, ctx)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    click.echo(f"Rendered {template} -> {dest}")


@main.command("deploy")
@click.argument("local")
@click.argument("remote")
@click.option("--inventory", "-i", default="examples/inventory.yml")
def deploy(local, remote, inventory):
    inv = Inventory.from_yaml(inventory)
    res = deploy_file(inv, local, remote)
    for host, info in res.items():
        if info.get("ok"):
            click.echo(f"{host}: ok")
        else:
            click.echo(f"{host}: error: {info.get('error')}")


@main.command("playbook")
@click.argument("playbook")
@click.option("--inventory", "-i", default="examples/inventory.yml")
def playbook(playbook, inventory):
    inv = Inventory.from_yaml(inventory)
    res = run_playbook(inv, playbook)
    # simple print of results
    for play in res:
        click.echo(f"Play: {play.get('name')}")
        for k, v in play.items():
            if k == "name":
                continue
            click.echo(f"  Task: {k}")
            click.echo(f"    {v}")


if __name__ == "__main__":
    main()
