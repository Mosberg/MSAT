import threading
from typing import Dict, Any
from .sshclient import SSHClient


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
