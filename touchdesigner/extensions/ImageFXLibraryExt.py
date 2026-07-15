"""TouchDesigner extension for browsing and instantiating TD ImageFX packages."""

from __future__ import annotations

import json
import re
from pathlib import Path


class ImageFXLibraryExt:
    """Public API exposed by the ``td_imagefx`` Base COMP."""

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def _root(self) -> Path:
        root_par = self.ownerComp.par["Rootfolder"]
        value = str(root_par.eval()).strip() if root_par is not None else ""
        return Path(value or project.folder).resolve()

    def _manifests(self):
        root = self._root()
        for path in sorted((root / "packages").glob("*/**/package.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                debug("TD ImageFX: unable to read", path, exc)
                continue
            data["_manifest_path"] = str(path)
            yield data

    @property
    def PackageIds(self):
        return [item["id"] for item in self._manifests()]

    def RefreshCatalog(self):
        """Rebuild the internal catalog DAT from immutable package manifests."""
        table = self.ownerComp.op("catalog")
        if table is None:
            raise RuntimeError("catalog DAT is missing")
        table.setSize(0, 0)
        table.appendRow(("id", "name", "version", "kind", "category", "channel", "stateful", "tags", "component"))
        count = 0
        for item in self._manifests():
            entrypoints = item.get("entrypoints", {})
            table.appendRow((
                item.get("id", ""),
                item.get("name", ""),
                item.get("version", ""),
                item.get("kind", ""),
                item.get("category", ""),
                item.get("channel", ""),
                str(bool(item.get("stateful", False))),
                ", ".join(item.get("tags", [])),
                entrypoints.get("touchdesigner_component", ""),
            ))
            count += 1
        if self.ownerComp.par.Status:
            self.ownerComp.par.Status = "Ready: {} packages".format(count)
        return count

    def Find(self, text="", category="", tags=None):
        """Return manifest dictionaries matching free text, category, and tags."""
        needle = str(text).strip().lower()
        category = str(category).strip().lower()
        wanted_tags = {str(tag).lower() for tag in (tags or [])}
        results = []
        for item in self._manifests():
            item_tags = {str(tag).lower() for tag in item.get("tags", [])}
            haystack = " ".join((
                item.get("id", ""),
                item.get("name", ""),
                item.get("description", ""),
                " ".join(item_tags),
            )).lower()
            if needle and needle not in haystack:
                continue
            if category and str(item.get("category", "")).lower() != category:
                continue
            if wanted_tags and not wanted_tags.issubset(item_tags):
                continue
            results.append(item)
        return results

    def PackageInfo(self, package_id, version=None):
        matches = [item for item in self._manifests() if item.get("id") == package_id]
        if version is not None:
            matches = [item for item in matches if item.get("version") == version]
        if not matches:
            raise KeyError("Unknown package: {} {}".format(package_id, version or ""))
        matches.sort(key=lambda item: tuple(int(part) for part in item["version"].split("-")[0].split(".")), reverse=True)
        return matches[0]

    def CreateEffect(self, package_id, target=None, version=None, name=None):
        """Create a package instance under ``target`` and return the Base COMP."""
        manifest = self.PackageInfo(package_id, version)
        entrypoint = manifest.get("entrypoints", {}).get("touchdesigner_component")
        if not entrypoint:
            raise RuntimeError("Package has no TouchDesigner component entrypoint")
        package_root = Path(manifest["_manifest_path"]).parent
        tox_path = (package_root / entrypoint).resolve()
        if not tox_path.is_file():
            raise FileNotFoundError(str(tox_path))
        target = target or self.ownerComp.parent()
        safe_name = name or re.sub(r"[^A-Za-z0-9_]", "_", package_id.split(".")[-1])
        before_ids = {child.id for child in target.children}
        target.loadTox(str(tox_path))
        created = [child for child in target.children if child.id not in before_ids]
        if len(created) != 1:
            raise RuntimeError("Expected one top-level component in {}".format(tox_path))
        instance = created[0]
        instance.name = safe_name
        return instance

    def CheckUpdates(self):
        updater = self.ownerComp.op("update_manager")
        if updater is None or not hasattr(updater, "CheckUpdates"):
            raise RuntimeError("Update Manager is unavailable")
        return updater.CheckUpdates()

    def HealthCheck(self):
        """Return a small diagnostic object suitable for a DAT or Textport."""
        missing = []
        for item in self._manifests():
            package_root = Path(item["_manifest_path"]).parent
            for entry_name, relative in item.get("entrypoints", {}).items():
                if not (package_root / relative).is_file():
                    missing.append({"id": item.get("id"), "entrypoint": entry_name, "path": relative})
        return {
            "ok": not missing,
            "package_count": len(self.PackageIds),
            "missing_entrypoints": missing,
            "touchdesigner_version": str(app.version),
            "touchdesigner_build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        }
