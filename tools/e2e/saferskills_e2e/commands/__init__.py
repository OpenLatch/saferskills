"""Command registry.

`ALL_COMMANDS` maps the CLI name -> the concrete command class. The CLI
dispatcher (in `cli.py`) iterates this dict to register argparse
subcommands.

`COMMAND_SEQUENCE` is the ordered list of names that `all` runs. `all`
itself is NOT in the sequence — running `all` from inside `all` would
recurse forever.
"""

from __future__ import annotations

from saferskills_e2e.commands.all import AllCommand
from saferskills_e2e.commands.badge_endpoint import BadgeEndpointCommand
from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.commands.doctor import DoctorCommand
from saferskills_e2e.commands.homepage import HomepageCommand
from saferskills_e2e.commands.item_detail import ItemDetailCommand
from saferskills_e2e.commands.og_endpoint import OgEndpointCommand
from saferskills_e2e.commands.smoke import SmokeCommand
from saferskills_e2e.commands.vendor_respond import VendorRespondCommand

ALL_COMMANDS: dict[str, type[BaseCommand]] = {
    DoctorCommand.name: DoctorCommand,
    SmokeCommand.name: SmokeCommand,
    HomepageCommand.name: HomepageCommand,
    ItemDetailCommand.name: ItemDetailCommand,
    VendorRespondCommand.name: VendorRespondCommand,
    BadgeEndpointCommand.name: BadgeEndpointCommand,
    OgEndpointCommand.name: OgEndpointCommand,
    AllCommand.name: AllCommand,
}

COMMAND_SEQUENCE: list[str] = [
    DoctorCommand.name,
    SmokeCommand.name,
    HomepageCommand.name,
    ItemDetailCommand.name,
    VendorRespondCommand.name,
    BadgeEndpointCommand.name,
    OgEndpointCommand.name,
]

__all__ = ["ALL_COMMANDS", "COMMAND_SEQUENCE"]
