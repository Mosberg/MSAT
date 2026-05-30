import paramiko
from typing import Optional, Dict


class SSHClient:
    def __init__(self, hostname: str, username: str = "root", port: int = 22, key_filename: Optional[str] = None, password: Optional[str] = None, timeout: int = 10):
        self.hostname = hostname
        self.username = username
        self.port = port
        self.key_filename = key_filename
        self.password = password
        self.timeout = timeout
        self.client = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.hostname, port=self.port, username=self.username,
                            key_filename=self.key_filename, password=self.password,
                            timeout=self.timeout)

    def run(self, command: str, timeout: Optional[int] = None) -> Dict[str, object]:
        if self.client is None:
            self.connect()
        stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        return {"exit_code": exit_status, "stdout": out, "stderr": err}

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
