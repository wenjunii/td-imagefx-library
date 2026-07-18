"""TouchDesigner extension for browsing and instantiating TD ImageFX packages."""

from __future__ import annotations

import json
import re
from pathlib import Path


VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

CATALOG_COLUMNS = (
    "id", "name", "version", "kind", "category", "channel", "description", "stateful", "tags",
    "processing_model", "gpu_cost", "capabilities", "quality", "compatibility",
    "compatibility_confidence", "preview", "input_count", "input_roles", "input_readiness",
    "parameter_count", "parameters", "alpha_policy", "resolution_policy", "image_contract", "component",
)

_AUXILIARY_ROLE_ALIASES = {
    "image_b": "image_b",
    "second_image": "image_b",
    "second_input": "image_b",
    "auxiliary_image": "image_b",
    "transition_image": "image_b",
    "transition": "image_b",
    "reference": "image_b",
    "reference_image": "image_b",
    "clean_plate": "image_b",
    "background": "image_b",
    "displacement": "displacement",
    "displacement_map": "displacement",
    "depth": "depth",
    "depth_map": "depth",
    "normal": "normal",
    "normal_map": "normal",
    "normals": "normal",
    "flow": "flow",
    "optical_flow": "flow",
    "motion": "flow",
    "motion_vectors": "flow",
    "mask": "mask",
    "matte": "mask",
}


def _normalized_role(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _repair_effect_shader_paths(root_comp):
    """Repair legacy absolute GLSL Pixel Shader paths in a loaded package."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        name = str(getattr(operator, "name", ""))
        if str(getattr(operator, "type", "")) != "glsl" or not name.startswith(
            "effect_glsl_"
        ):
            continue
        shader_name = "pixel_shader_" + name[len("effect_glsl_"):]
        shader_dat = operator.parent().op(shader_name)
        parameter = operator.par["pixeldat"]
        if shader_dat is None or parameter is None:
            raise RuntimeError(
                "{} is missing its portable Pixel Shader DAT".format(operator.path)
            )
        parameter.val = operator.relativePath(shader_dat)
        if parameter.eval() != shader_dat:
            raise RuntimeError(
                "{} Pixel Shader reference did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def _repair_effect_callback_paths(root_comp):
    """Repair legacy absolute reset callback targets in a loaded package."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        if str(getattr(operator, "name", "")) != "reset_callbacks":
            continue
        parameter = operator.par["op"]
        target = operator.parent()
        if parameter is None or target is None:
            raise RuntimeError(
                "{} is missing its portable reset callback target".format(operator.path)
            )
        parameter.val = operator.relativePath(target)
        if parameter.eval() != target:
            raise RuntimeError(
                "{} reset callback target did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def _repair_effect_state_paths(root_comp):
    """Repair legacy absolute Feedback TOP targets in a loaded package."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        if str(getattr(operator, "name", "")) != "history_feedback":
            continue
        target = operator.parent().op("state_target")
        parameter = operator.par["top"]
        if parameter is None or target is None:
            raise RuntimeError(
                "{} is missing its portable state target".format(operator.path)
            )
        parameter.val = operator.relativePath(target)
        if parameter.eval() != target:
            raise RuntimeError(
                "{} Feedback TOP target did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def _manifest_input_roles(manifest):
    roles = []
    for input_index, definition in enumerate(manifest.get("inputs") or []):
        if input_index == 0:
            roles.append("image")
            continue
        definition = definition if isinstance(definition, dict) else {}
        role = None
        for candidate in (
            definition.get("role"),
            definition.get("semantic"),
            definition.get("id"),
        ):
            role = _AUXILIARY_ROLE_ALIASES.get(_normalized_role(candidate))
            if role is not None:
                break
        role = role or _normalized_role(
            definition.get("role")
            or definition.get("semantic")
            or definition.get("id")
            or "input_{}".format(input_index + 1)
        )
        roles.append(role or "input_{}".format(input_index + 1))
    return tuple(roles or ("image",))


def _manifest_parameter_summary(manifest):
    summaries = []
    for definition in manifest.get("parameters") or []:
        if not isinstance(definition, dict):
            continue
        name = str(definition.get("name") or definition.get("id") or "parameter")
        label = str(definition.get("label") or name)
        details = [str(definition.get("type") or "float")]
        if definition.get("unit"):
            details.append(str(definition["unit"]))
        if definition.get("animatable", True) is False:
            details.append("constant")
        summaries.append("{} ({})".format(label, ", ".join(details)))
    return "; ".join(summaries)


def _manifest_image_contract(manifest):
    contract = manifest.get("image_contract") or {}
    if not isinstance(contract, dict) or not contract:
        return "legacy manifest contract"
    color = contract.get("color") or {}
    alpha = contract.get("alpha") or {}
    pixel = contract.get("pixel_format") or {}
    sampling = contract.get("sampling") or {}
    return " | ".join((
        "color {}>{}>{} ({})".format(
            color.get("input_space", "?"), color.get("working_space", "?"),
            color.get("output_space", "?"), color.get("reference", "?"),
        ),
        "alpha {}>{}>{}".format(
            alpha.get("input", "?"), alpha.get("working", "?"), alpha.get("output", "?"),
        ),
        "pixel {}{}".format(
            pixel.get("policy", "?"), ":{}".format(pixel["format"]) if pixel.get("format") else "",
        ),
        "sampling {}/{}{}".format(
            sampling.get("filter", "?"), sampling.get("edge", "?"),
            "/mipmaps" if sampling.get("mipmaps") else "",
        ),
    ))


def _manifest_quality(manifest):
    processing = manifest.get("processing") or {}
    tiers = []
    for item in processing.get("quality_tiers") or []:
        if isinstance(item, dict):
            value = item.get("label") or item.get("id")
        else:
            value = item
        if value:
            tiers.append(str(value))
    channel = str(manifest.get("channel") or "unknown")
    maturity = {
        "stable": "curated stable",
        "beta": "curated beta",
        "experimental": "experimental",
    }.get(channel, channel)
    return "{} ({})".format(maturity, ", ".join(tiers)) if tiers else maturity


def _manifest_catalog_row(manifest, compatibility_confidence="declared"):
    processing = manifest.get("processing") or {}
    compatibility = manifest.get("compatibility") or {}
    entrypoints = manifest.get("entrypoints") or {}
    roles = _manifest_input_roles(manifest)
    parameters = manifest.get("parameters") or []
    systems = compatibility.get("os") or []
    architectures = compatibility.get("architectures") or []
    return {
        "id": manifest.get("id", ""),
        "name": manifest.get("name", ""),
        "version": manifest.get("version", ""),
        "kind": manifest.get("kind", ""),
        "category": manifest.get("category", ""),
        "channel": manifest.get("channel", ""),
        "description": manifest.get("description", ""),
        "stateful": str(bool(manifest.get("stateful", False))),
        "tags": ", ".join(str(value) for value in (manifest.get("tags") or [])),
        "processing_model": processing.get("model", "single_pass"),
        "gpu_cost": processing.get("gpu_cost", "low"),
        "capabilities": ", ".join(str(value) for value in (processing.get("capabilities") or [])),
        "quality": _manifest_quality(manifest),
        "compatibility": "TD {}+ | {} | {}".format(
            compatibility.get("touchdesigner_min_build", "unknown"),
            ",".join(str(value) for value in systems),
            ",".join(str(value) for value in architectures),
        ),
        "compatibility_confidence": compatibility_confidence or "declared",
        "preview": "docs/gallery/{}.png".format(manifest.get("id", "")),
        "input_count": str(len(roles)),
        "input_roles": ", ".join(roles),
        "input_readiness": "Ready" if len(roles) == 1 else "Needs {}".format(", ".join(roles[1:])),
        "parameter_count": str(len(parameters)),
        "parameters": _manifest_parameter_summary(manifest),
        "alpha_policy": manifest.get("alpha_policy", "unspecified"),
        "resolution_policy": manifest.get("resolution_policy", "unspecified"),
        "image_contract": _manifest_image_contract(manifest),
        "component": entrypoints.get("touchdesigner_component", ""),
    }


def _catalog_confidence(table):
    """Preserve native-verification labels for unchanged catalog identities."""
    try:
        rows = list(table.rows())
    except (AttributeError, TypeError):
        return {}
    if not rows:
        return {}
    headers = [str(cell) for cell in rows[0]]
    try:
        id_index = headers.index("id")
        version_index = headers.index("version")
        confidence_index = headers.index("compatibility_confidence")
    except ValueError:
        return {}
    result = {}
    for row in rows[1:]:
        if max(id_index, version_index, confidence_index) >= len(row):
            continue
        package_id = str(row[id_index]).strip()
        version = str(row[version_index]).strip()
        confidence = str(row[confidence_index]).strip()
        if package_id and version and confidence:
            result[(package_id, version)] = confidence
    return result


class ImageFXLibraryExt:
    """Public API exposed by the ``td_imagefx`` Base COMP."""

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def _root(self) -> Path:
        root_par = self.ownerComp.par["Rootfolder"]
        value = str(root_par.eval()).strip() if root_par is not None else ""
        return Path(value or project.folder).resolve()

    @staticmethod
    def _version_key(version):
        core = version.split("+", 1)[0]
        release, separator, prerelease = core.partition("-")
        release_key = tuple(int(part) for part in release.split("."))
        if not separator:
            return release_key, 1, ()
        prerelease_key = tuple(
            (0, int(part)) if part.isdigit() else (1, part.lower())
            for part in prerelease.split(".")
        )
        return release_key, 0, prerelease_key

    def _all_manifests(self):
        root = self._root()
        for path in sorted((root / "packages").glob("*/**/package.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                debug("TD ImageFX: unable to read", path, exc)
                continue
            package_id = data.get("id")
            version = data.get("version")
            if not isinstance(package_id, str) or not isinstance(version, str) or not VERSION_RE.fullmatch(version):
                debug("TD ImageFX: invalid package identity", path)
                continue
            data["_manifest_path"] = str(path)
            yield data

    def _manifests(self):
        latest = {}
        for item in self._all_manifests():
            package_id = item["id"]
            current = latest.get(package_id)
            if current is None or self._version_key(current["version"]) < self._version_key(item["version"]):
                latest[package_id] = item
        for package_id in sorted(latest):
            yield latest[package_id]

    @property
    def PackageIds(self):
        return [item["id"] for item in self._manifests()]

    def RefreshCatalog(self):
        """Rebuild the full browser catalog from immutable package manifests."""
        table = self.ownerComp.op("catalog")
        if table is None:
            raise RuntimeError("catalog DAT is missing")
        confidence_by_identity = _catalog_confidence(table)
        table.setSize(0, 0)
        table.appendRow(CATALOG_COLUMNS)
        count = 0
        for item in self._manifests():
            identity = (item["id"], item["version"])
            row = _manifest_catalog_row(
                item,
                confidence_by_identity.get(identity, "declared"),
            )
            table.appendRow(tuple(row[column] for column in CATALOG_COLUMNS))
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
                str((item.get("processing") or {}).get("model", "")),
                " ".join((item.get("processing") or {}).get("capabilities", [])),
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
        source = self._all_manifests() if version is not None else self._manifests()
        matches = [item for item in source if item.get("id") == package_id]
        if version is not None:
            matches = [item for item in matches if item.get("version") == version]
        if not matches:
            raise KeyError("Unknown package: {} {}".format(package_id, version or ""))
        matches.sort(key=lambda item: self._version_key(item["version"]), reverse=True)
        return matches[0]

    def CreateEffect(self, package_id, target=None, version=None, name=None):
        """Create a package instance under ``target`` and return the Base COMP."""
        manifest = self.PackageInfo(package_id, version)
        entrypoint = manifest.get("entrypoints", {}).get("touchdesigner_component")
        if not entrypoint:
            raise RuntimeError("Package has no TouchDesigner component entrypoint")
        package_root = Path(manifest["_manifest_path"]).parent
        tox_path = (package_root / entrypoint).resolve()
        try:
            tox_path.relative_to(package_root.resolve())
        except ValueError as exc:
            raise RuntimeError("TouchDesigner component escapes its package") from exc
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
        try:
            instance.name = safe_name
            _repair_effect_shader_paths(instance)
            _repair_effect_callback_paths(instance)
            _repair_effect_state_paths(instance)
        except Exception:
            try:
                instance.destroy()
            except Exception:
                pass
            raise
        return instance

    def CheckUpdates(self):
        updater = self.ownerComp.op("update_manager")
        if updater is None or not hasattr(updater, "CheckUpdates"):
            raise RuntimeError("Update Manager is unavailable")
        return updater.CheckUpdates()

    def HealthCheck(self):
        """Return a small diagnostic object suitable for a DAT or Textport."""
        missing = []
        all_manifests = list(self._all_manifests())
        for item in all_manifests:
            package_root = Path(item["_manifest_path"]).parent
            for entry_name, relative in item.get("entrypoints", {}).items():
                if not relative or not (package_root / relative).is_file():
                    missing.append({"id": item.get("id"), "entrypoint": entry_name, "path": relative})
            for pass_index, relative in enumerate((item.get("processing") or {}).get("passes", [])):
                if not relative or not (package_root / relative).is_file():
                    missing.append({"id": item.get("id"), "entrypoint": "pass{}".format(pass_index + 1), "path": relative})
        return {
            "ok": not missing,
            "package_count": len(self.PackageIds),
            "package_version_count": len(all_manifests),
            "missing_entrypoints": missing,
            "touchdesigner_version": str(app.version),
            "touchdesigner_build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        }
