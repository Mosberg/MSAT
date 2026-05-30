import os
import yaml
import tempfile

from mosberg import tasks


class DummySSHClient:
    def __init__(self, hostname, username="root", port=22, key_filename=None, password=None, timeout=10):
        self.hostname = hostname
        self.username = username
        self.port = port
        self.put_calls = []
        self.put_data_calls = []
        self.run_calls = []

    def run(self, command, timeout=None):
        self.run_calls.append(command)
        return {"exit_code": 0, "stdout": f"out:{command}", "stderr": ""}

    def put(self, local_path, remote_path):
        self.put_calls.append((local_path, remote_path))

    def put_data(self, data, remote_path):
        self.put_data_calls.append((data, remote_path))

    def close(self):
        return None


def test_deploy_and_playbook(monkeypatch, tmp_path):
    # monkeypatch the SSHClient used inside tasks
    monkeypatch.setattr(tasks, "SSHClient", DummySSHClient)

    hosts = [{"name": "host1", "host": "127.0.0.1", "user": "tester", "vars": {"greeting": "world"}}]
    Inv = type("Inv", (), {"hosts": hosts})

    # create a local file to deploy
    local_file = tmp_path / "file.txt"
    local_file.write_text("hello")

    # test deploy_file
    res = tasks.deploy_file(Inv, str(local_file), "/tmp/remote.txt")
    assert "host1" in res
    assert res["host1"]["ok"] is True

    # create a template
    tpl = tmp_path / "tpl.j2"
    tpl.write_text("Greeting: {{ greeting }}")

    # create playbook
    playbook = [
        {
            "name": "testplay",
            "hosts": "all",
            "vars": {},
            "tasks": [
                {"name": "echo", "command": "echo hi"},
                {"name": "copy", "copy": {"src": str(local_file), "dest": "/tmp/remote.txt"}},
                {"name": "template", "template": {"src": str(tpl), "dest": "/tmp/remote.tpl"}},
                {"name": "script", "script": {"src": str(local_file), "args": ""}},
                {"name": "service", "service": {"name": "nginx", "state": "restart"}},
                {"name": "package", "package": {"name": "curl", "state": "present", "manager": "apt"}},
            ],
        }
    ]

    pbfile = tmp_path / "playbook.yml"
    pbfile.write_text(yaml.safe_dump(playbook))

    out = tasks.run_playbook(Inv, str(pbfile))
    assert isinstance(out, list)
    playres = out[0]
    assert any(t["name"] == "echo" for t in playres["tasks"])

    echo_task = next(t for t in playres["tasks"] if t["name"] == "echo")
    assert "host1" in echo_task["hosts"]
    assert echo_task["hosts"]["host1"]["ok"] is True

    copy_task = next(t for t in playres["tasks"] if t["name"] == "copy")
    assert copy_task["hosts"]["host1"]["ok"] is True

    template_task = next(t for t in playres["tasks"] if t["name"] == "template")
    assert template_task["hosts"]["host1"]["ok"] is True

    script_task = next(t for t in playres["tasks"] if t["name"] == "script")
    assert script_task["hosts"]["host1"]["ok"] is True

    svc_task = next(t for t in playres["tasks"] if t["name"] == "service")
    pkg_task = next(t for t in playres["tasks"] if t["name"] == "package")
    assert svc_task["hosts"]["host1"]["ok"] is True
    assert pkg_task["hosts"]["host1"]["ok"] is True
