import os
import threading
from typing import Any, Dict, Optional

import yaml

from .sshclient import SSHClient
from .templates import render_template


def _make_result_from_exec(
    exec_res: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None
) -> Dict[str, Any]:
    if exec_res is None:
        exec_res = {}
    exit_code = exec_res.get("exit_code")
    stdout = exec_res.get("stdout", "")
    stderr = exec_res.get("stderr", "")
    ok = None
    if exit_code is not None:
        ok = exit_code == 0
    else:
        ok = error is None
    out = {"ok": ok, "exit_code": exit_code, "stdout": stdout, "stderr": stderr}
    if error:
        out["error"] = str(error)
    return out


def run_command(
    inventory, command: str, concurrency: int = 5, ssh_kwargs: Dict[str, Any] = None
) -> Dict[str, Dict[str, Any]]:
    """Run a shell command on all hosts in the inventory in parallel.

    Returns a mapping host_name -> result where result contains keys: ok, exit_code, stdout, stderr, and error (if exception).
    """
    results: Dict[str, Dict[str, Any]] = {}
    lock = threading.Lock()
    ssh_kwargs = ssh_kwargs or {}

    def worker(host):
        name = host.get("name") or host.get("host")
        hostname = host["host"]
        user = host.get("user") or "root"
        client = SSHClient(
            hostname, username=user, port=host.get("port", 22), **ssh_kwargs
        )
        try:
            res = client.run(command)
            out = _make_result_from_exec(res)
            with lock:
                results[name] = out
        except Exception as e:
            with lock:
                results[name] = _make_result_from_exec(None, e)
        finally:
            try:
                client.close()
            except Exception:
                pass

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


def deploy_file(
    inventory,
    local_path: str,
    remote_path: str,
    concurrency: int = 5,
    ssh_kwargs: Dict[str, Any] = None,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    lock = threading.Lock()
    ssh_kwargs = ssh_kwargs or {}

    def worker(host):
        name = host.get("name") or host.get("host")
        hostname = host["host"]
        user = host.get("user") or "root"
        client = SSHClient(
            hostname, username=user, port=host.get("port", 22), **ssh_kwargs
        )
        try:
            client.put(local_path, remote_path)
            with lock:
                results[name] = {"ok": True}
        except Exception as e:
            with lock:
                results[name] = {"ok": False, "error": str(e)}
        finally:
            try:
                client.close()
            except Exception:
                pass

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
    out = [
        h
        for h in inventory.hosts
        if (h.get("name") in wanted or h.get("host") in wanted)
    ]
    return out


def run_playbook(
    inventory,
    playbook_path: str,
    concurrency: int = 5,
    ssh_kwargs: Dict[str, Any] = None,
) -> list:
    """Run a simple playbook with supported task types: command, copy, template, script, service, package.

    Returns a list of played plays. Each play contains `name` and `tasks` (a list). Each task contains `name`, `type` and `hosts` mapping host -> result dict.
    """
    ssh_kwargs = ssh_kwargs or {}
    with open(playbook_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    plays = data if isinstance(data, list) else [data]
    overall = []
    for play in plays:
        hosts_sel = play.get("hosts", "all")
        hosts = _filter_hosts(inventory, hosts_sel)
        play_vars = play.get("vars", {}) or {}
        play_result = {"name": play.get("name"), "tasks": []}

        for task in play.get("tasks", []):
            # determine task type
            t_name = task.get("name") or "unnamed"
            if "command" in task:
                ttype = "command"
                cmd = task["command"]
                tmp = type("Inv", (), {"hosts": hosts})
                res = run_command(
                    tmp, cmd, concurrency=concurrency, ssh_kwargs=ssh_kwargs
                )
                task_result = {"name": t_name, "type": ttype, "hosts": res}

            elif "copy" in task or (
                "src" in task and "dest" in task and task.get("action") == "copy"
            ):
                ttype = "copy"
                entry = task.get("copy") or task
                src = entry.get("src")
                dest = entry.get("dest")
                tmp = type("Inv", (), {"hosts": hosts})
                res = deploy_file(
                    tmp, src, dest, concurrency=concurrency, ssh_kwargs=ssh_kwargs
                )
                task_result = {"name": t_name, "type": ttype, "hosts": res}

            elif "template" in task:
                ttype = "template"
                entry = task.get("template")
                src = entry.get("src")
                dest = entry.get("dest")
                t_res: Dict[str, Any] = {}
                threads = []

                def tmpl_worker(host):
                    name = host.get("name") or host.get("host")
                    ctx = {}
                    ctx.update(play_vars)
                    ctx.update(host.get("vars", {}) or {})
                    try:
                        content = render_template(src, ctx)
                    except Exception as e:
                        t_res[name] = {"ok": False, "error": f"render error: {e}"}
                        return
                    client = SSHClient(
                        host.get("host"),
                        username=host.get("user") or "root",
                        port=host.get("port", 22),
                        **ssh_kwargs,
                    )
                    try:
                        client.put_data(content.encode("utf-8"), dest)
                        t_res[name] = {"ok": True}
                    except Exception as e:
                        t_res[name] = {"ok": False, "error": str(e)}
                    finally:
                        try:
                            client.close()
                        except Exception:
                            pass

                for host in hosts:
                    tt = threading.Thread(target=tmpl_worker, args=(host,))
                    tt.start()
                    threads.append(tt)
                    while len([xx for xx in threads if xx.is_alive()]) >= concurrency:
                        for xx in threads:
                            xx.join(0.1)
                for tt in threads:
                    tt.join()
                task_result = {"name": t_name, "type": ttype, "hosts": t_res}

            elif "script" in task:
                ttype = "script"
                entry = task.get("script")
                src = entry.get("src")
                args = entry.get("args", "")
                t_res: Dict[str, Any] = {}
                threads = []

                def script_worker(host):
                    name = host.get("name") or host.get("host")
                    client = SSHClient(
                        host.get("host"),
                        username=host.get("user") or "root",
                        port=host.get("port", 22),
                        **ssh_kwargs,
                    )
                    remote_tmp = f"/tmp/{os.path.basename(src)}"
                    try:
                        client.put(src, remote_tmp)
                        cmd = f"chmod +x {remote_tmp} && {remote_tmp} {args}".strip()
                        exec_res = client.run(cmd)
                        t_res[name] = _make_result_from_exec(exec_res)
                    except Exception as e:
                        t_res[name] = {"ok": False, "error": str(e)}
                    finally:
                        try:
                            client.close()
                        except Exception:
                            pass

                for host in hosts:
                    tt = threading.Thread(target=script_worker, args=(host,))
                    tt.start()
                    threads.append(tt)
                    while len([xx for xx in threads if xx.is_alive()]) >= concurrency:
                        for xx in threads:
                            xx.join(0.1)
                for tt in threads:
                    tt.join()
                task_result = {"name": t_name, "type": ttype, "hosts": t_res}

            elif "service" in task:
                ttype = "service"
                entry = task.get("service")
                svc_name = entry.get("name")
                state = entry.get("state", "restart")
                cmd = ""
                if state in ("start", "started"):
                    cmd = f"sudo systemctl start {svc_name}"
                elif state in ("stop", "stopped"):
                    cmd = f"sudo systemctl stop {svc_name}"
                elif state in ("restart", "restarted"):
                    cmd = f"sudo systemctl restart {svc_name}"
                elif state in ("enable", "enabled"):
                    cmd = f"sudo systemctl enable {svc_name}"
                elif state in ("disable", "disabled"):
                    cmd = f"sudo systemctl disable {svc_name}"
                else:
                    cmd = f"sudo systemctl {state} {svc_name}"
                tmp = type("Inv", (), {"hosts": hosts})
                res = run_command(
                    tmp, cmd, concurrency=concurrency, ssh_kwargs=ssh_kwargs
                )
                task_result = {"name": t_name, "type": ttype, "hosts": res}

            elif "package" in task:
                ttype = "package"
                entry = task.get("package")
                pkg_name = entry.get("name")
                state = entry.get("state", "present")
                manager = entry.get("manager", "apt")
                if state in ("present", "install", "installed"):
                    if manager == "apt":
                        cmd = f"sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_name}"
                    else:
                        cmd = f"sudo {manager} install -y {pkg_name}"
                elif state in ("absent", "remove", "purge"):
                    if manager == "apt":
                        cmd = f"sudo apt-get remove -y {pkg_name}"
                    else:
                        cmd = f"sudo {manager} remove -y {pkg_name}"
                else:
                    cmd = f"sudo {manager} install -y {pkg_name}"
                tmp = type("Inv", (), {"hosts": hosts})
                res = run_command(
                    tmp, cmd, concurrency=concurrency, ssh_kwargs=ssh_kwargs
                )
                task_result = {"name": t_name, "type": ttype, "hosts": res}

            else:
                task_result = {"name": t_name, "type": "unknown", "hosts": {}}

            play_result["tasks"].append(task_result)

        overall.append(play_result)
    return overall
