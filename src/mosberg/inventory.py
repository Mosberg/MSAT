import yaml
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Host:
    name: str
    host: str
    user: Optional[str] = "root"
    port: Optional[int] = 22
    vars: Dict[str, Any] = None


class Inventory:
    def __init__(self, hosts: List[Dict[str, Any]]):
        self.hosts = hosts

    @classmethod
    def from_yaml(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        hosts = data.get("hosts", [])
        return cls(hosts)
