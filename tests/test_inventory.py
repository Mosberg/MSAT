from mosberg.inventory import Inventory


def test_load_inventory():
    inv = Inventory.from_yaml("examples/inventory.yml")
    assert hasattr(inv, "hosts")
    assert len(inv.hosts) >= 1
