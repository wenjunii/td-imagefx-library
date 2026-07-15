"""TouchDesigner extension for the four-slot starter ImageFX rack."""

from __future__ import annotations

import json
import re
from pathlib import Path


class FxRackExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def _root(self) -> Path:
        root_par = self.ownerComp.par["Rootfolder"]
        value = str(root_par.eval()).strip() if root_par is not None else ""
        return Path(value or project.folder).resolve()

    def _find_manifest(self, package_id, version=None):
        matches = []
        for path in (self._root() / "packages" / package_id).glob("*/package.json"):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if version is None or manifest.get("version") == version:
                matches.append((manifest, path))
        if not matches:
            raise KeyError("Package is not installed: {} {}".format(package_id, version or ""))
        matches.sort(key=lambda pair: tuple(int(x) for x in pair[0]["version"].split("-")[0].split(".")), reverse=True)
        return matches[0]

    def _slot_source(self, index):
        if index == 1:
            return self.ownerComp.op("in1_image")
        return self.ownerComp.op("slot{}".format(index - 1))

    def _connect_slot(self, index, slot):
        source = self._slot_source(index)
        source_connector = source.outputConnectors[0]
        source_connector.connect(slot.inputConnectors[0])
        if len(slot.inputConnectors) > 1:
            self.ownerComp.op("in1_image").outputConnectors[0].connect(slot.inputConnectors[1])
        next_slot = self.ownerComp.op("slot{}".format(index + 1)) if index < 4 else self.ownerComp.op("out1_image")
        if next_slot is not None:
            target_connector = next_slot.inputConnectors[0]
            slot.outputConnectors[0].connect(target_connector)

    def LoadSlot(self, index, package_id=None, version=None):
        """Load an immutable package into a rack slot without changing other slots."""
        index = int(index)
        if index < 1 or index > 4:
            raise ValueError("Slot index must be between 1 and 4")
        menu_par = self.ownerComp.par["Slot{}effect".format(index)]
        package_id = package_id or menu_par.eval()
        manifest, manifest_path = self._find_manifest(package_id, version)
        relative = manifest.get("entrypoints", {}).get("touchdesigner_component")
        if not relative:
            raise RuntimeError("Package has no TouchDesigner component")
        tox_path = (manifest_path.parent / relative).resolve()
        if not tox_path.is_file():
            raise FileNotFoundError(str(tox_path))
        old_slot = self.ownerComp.op("slot{}".format(index))
        before_ids = {child.id for child in self.ownerComp.children}
        self.ownerComp.loadTox(str(tox_path))
        created = [child for child in self.ownerComp.children if child.id not in before_ids]
        if len(created) != 1:
            raise RuntimeError("Expected one top-level component in {}".format(tox_path))
        slot = created[0]
        if old_slot is not None:
            old_slot.destroy()
        slot.name = "slot{}".format(index)
        self._connect_slot(index, slot)
        enable_par = slot.par["Enable"]
        mix_par = slot.par["Mix"]
        if enable_par is not None:
            enable_par.expr = "parent().par.Slot{}enable".format(index)
        if mix_par is not None:
            mix_par.expr = "parent().par.Slot{}mix".format(index)
        if slot.par["Time"] is not None:
            slot.par.Time.expr = "parent().par.Time"
        self.ownerComp.store("slot{}_package".format(index), {"id": package_id, "version": manifest["version"]})
        return slot

    def ReloadAll(self):
        return [self.LoadSlot(index) for index in range(1, 5)]

    def Reset(self):
        for index in range(1, 5):
            slot = self.ownerComp.op("slot{}".format(index))
            if slot is not None and slot.par["Reset"] is not None:
                slot.par.Reset.pulse()

    def State(self):
        return {
            "slots": [self.ownerComp.fetch("slot{}_package".format(index), None) for index in range(1, 5)],
            "time": float(self.ownerComp.par.Time),
        }
