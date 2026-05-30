import threading
from typing import Dict, Any
from .sshclient import SSHClient
import yaml
import os
from .templates import render_template


def run_command(inventory, command: str, concurrency: int = 5, ssh_kwargs: Dict[str, Any] = None):
    results = {}
    lock = threading.Lock()
    ssh_kwargs = ssh_kwargs or {}

    def worker(host):
        name = host.get("name") or host.get("host")
        hostname = host["host"]
        user = host.get("user") or "root"
        client = SSHClient(hostname, username=user, port=host.get("port", 22), **ssh_kwargs)
        try:
            res = client.run(command)
            with lock:
                results[name] = res
        except Exception as e:
            with lock:
                results[name] = {"exit_code": -1, "stdout": "", "stderr": str(e)}
        finally:
            client.close()

    threads = []
    for host in inventory.hosts:
        t = threading.Thread(target=worker, args=(host,))
        t.start()
        threads.append(t)
        # simple concurrency limiter
        while len([tt for tt in threads if tt.is_alive()]) >= concurrency:
            for tt in threads:
                tt.join(0.1)
    for t in threads:
        t.join()
    return results


def deploy_file(inventory, local_path: str, remote_path: str, concurrency: int = 5, ssh_kwargs: Dict[str, Any] = None):
    results = {}
    lock = threading.Lock()
    ssh_kwargs = ssh_kwargs or {}

    def worker(host):
        name = host.get("name") or host.get("host")
        hostname = host["host"]
        user = host.get("user") or "root"
        client = SSHClient(hostname, username=user, port=host.get("port", 22), **ssh_kwargs)
        try:
            client.put(local_path, remote_path)
            with lock:
                results[name] = {"ok": True}
        except Exception as e:
            with lock:
                results[name] = {"ok": False, "error": str(e)}
        finally:
            client.close()

    threads = []
    for host in inventory.hosts:
        t = threading.Thread(target=worker, args=(host,))
        t.start()
        threads.append(t)
        while len([tt for tt in threads if tt.is_alive()]) >= concurrency:
            for tt in threads:
                tt.join(0.1)
    for t in threads:
        t.join()
    return results


def _filter_hosts(inventory, selector):
    if not selector or selector == "all":
        return inventory.hosts
    # support comma-separated host names
    wanted = [s.strip() for s in str(selector).split(",") if s.strip()]
    out = [h for h in inventory.hosts if (h.get("name") in wanted or h.get("host") in wanted)]
    return out


def run_playbook(inventory, playbook_path: str, concurrency: int = 5, ssh_kwargs: Dict[str, Any] = None):
    ssh_kwargs = ssh_kwargs or {}
    with open(playbook_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    plays = data if isinstance(data, list) else [data]
    overall = []
    for play in plays:
        hosts_sel = play.get("hosts", "all")
        hosts = _filter_hosts(inventory, hosts_sel)
        play_vars = play.get("vars", {}) or {}
        play_res = {"name": play.get("name"), "hosts": {}}
        for task in play.get("tasks", []):
            if "command" in task:
                cmd = task["command"]
                # create a temporary inventory object for selected hosts
                tmp = type("Inv", (), {"hosts": hosts})
                res = run_command(tmp, cmd, concurrency=concurrency, ssh_kwargs=ssh_kwargs)
                play_res[task.get("name", cmd)] = res
            elif "copy" in task or ("src" in task and "dest" in task and task.get("action") == "copy"):
                entry = task.get("copy") or task
                src = entry.get("src")
                dest = entry.get("dest")
                # deploy src file to dest on each host
                tmp = type("Inv", (), {"hosts": hosts})
                res = deploy_file(tmp, src, dest, concurrency=concurrency, ssh_kwargs=ssh_kwargs)
                play_res[task.get("name", f"copy {src} -> {dest}")] = res
            elif "template" in task:
                entry = task.get("template")
                src = entry.get("src")
                dest = entry.get("dest")
                t_res = {}
                # render per-host and upload
                threads = []

                def tmpl_worker(host):
                    name = host.get("name") or host.get("host")
                    ctx = {}
                    ctx.update(play_vars)
                    ctx.update(host.get("vars", {}) or {})
                    content = render_template(src, ctx)
                    client = SSHClient(host.get("host"), username=host.get("user") or "root", port=host.get("port", 22), **ssh_kwargs)
                    try:
                        client.put_data(content.encode("utf-8"), dest)
                        t_res[name] = {"ok": True}
                    except Exception as e:
                        t_res[name] = {"ok": False, "error": str(e)}
                    finally:
                        client.close()

                for host in hosts:
                    tt = threading.Thread(target=tmpl_worker, args=(host,))
                    tt.start()
                    threads.append(tt)
                    while len([xx for xx in threads if xx.is_alive()]) >= concurrency:
                        for xx in threads:
                            xx.join(0.1)
                for tt in threads:
                    tt.join()
                play_res[task.get("name", f"template {src} -> {dest}")] = t_res
        overall.append(play_res)
    return overall
