"""Searchable TouchDesigner browser for the TD ImageFX package catalog.

The functions above :class:`ImageFXBrowserExt` intentionally avoid TouchDesigner
globals.  They can be reused by documentation tools and tested in normal Python.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping


RESULT_COLUMNS = (
    "id",
    "name",
    "version",
    "category",
    "channel",
    "description",
    "tags",
    "favorite",
    "preview",
    "input_count",
    "input_roles",
    "input_readiness",
    "parameter_count",
    "parameters",
    "alpha_policy",
    "resolution_policy",
    "image_contract",
    "compatibility",
    "compatibility_confidence",
    "quality",
    "model",
    "gpu_cost",
    "capabilities",
    "component",
)

GPU_COST_ORDER = {"low": 0, "medium": 1, "high": 2, "very_high": 3, "unknown": 4}
MAX_VISIBLE_RESULTS = 24


def _text(value) -> str:
    """Return DAT cells and ordinary values as stripped text."""
    if value is None:
        return ""
    return str(value).strip()


def split_tags(value) -> tuple[str, ...]:
    """Normalize a comma-separated string or iterable into unique tag names."""
    if value is None:
        return ()
    values = value if isinstance(value, Iterable) and not isinstance(value, (str, bytes)) else str(value).split(",")
    result = []
    seen = set()
    for item in values:
        tag = _text(item)
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            result.append(tag)
    return tuple(result)


def parse_favorites(value) -> set[str]:
    """Read the JSON array stored in the browser's ``Favorites`` parameter.

    Malformed or non-array values are treated as an empty favorite set so a bad
    project parameter cannot prevent the browser from opening.
    """
    if value is None or _text(value) == "":
        return set()
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return set()
    if not isinstance(decoded, list):
        return set()
    return {_text(item) for item in decoded if isinstance(item, str) and _text(item)}


def serialize_favorites(favorites) -> str:
    """Serialize favorite IDs deterministically for stable project files."""
    normalized = sorted({_text(item) for item in (favorites or ()) if _text(item)}, key=str.casefold)
    return json.dumps(normalized, separators=(",", ":"), ensure_ascii=True)


def catalog_rows(table) -> list[dict[str, str]]:
    """Convert a TouchDesigner Table DAT (or compatible fake) to dictionaries."""
    if table is None:
        raise RuntimeError("library catalog DAT is missing")
    try:
        rows = list(table.rows())
    except (AttributeError, TypeError) as exc:
        raise TypeError("catalog must provide rows()") from exc
    if not rows:
        return []
    headers = [_text(cell) for cell in rows[0]]
    if not any(headers):
        return []
    result = []
    for values in rows[1:]:
        row = {header: _text(values[index]) if index < len(values) else "" for index, header in enumerate(headers) if header}
        if row.get("id"):
            result.append(row)
    return result


def _row_value(row: Mapping[str, object], *names: str) -> str:
    for name in names:
        value = _text(row.get(name, ""))
        if value:
            return value
    return ""


def compatibility_label(row: Mapping[str, object]) -> str:
    """Produce a compact compatibility label from old or expanded catalogs."""
    direct = _row_value(row, "compatibility", "compatible")
    if direct:
        return direct
    minimum = _row_value(row, "touchdesigner_min_build", "td_min_build", "min_build")
    maximum = _row_value(row, "touchdesigner_max_build", "td_max_build", "max_build")
    systems = _row_value(row, "os", "operating_systems")
    architectures = _row_value(row, "architectures", "architecture")
    parts = []
    if minimum and maximum:
        parts.append("TD {}-{}".format(minimum, maximum))
    elif minimum:
        parts.append("TD {}+".format(minimum))
    elif maximum:
        parts.append("TD <= {}".format(maximum))
    if systems:
        parts.append(systems)
    if architectures:
        parts.append(architectures)
    return " | ".join(parts) if parts else "Unknown"


def compatibility_confidence_label(row: Mapping[str, object]) -> str:
    """Return an honest confidence label separate from compatibility claims."""
    direct = _row_value(row, "compatibility_confidence", "compatibility_status")
    if direct:
        return direct
    if _row_value(row, "verified_build", "tested_build"):
        return "runtime verified"
    return "declared"


def quality_label(row: Mapping[str, object]) -> str:
    """Summarize package maturity and any declared processing quality tiers."""
    direct = _row_value(row, "quality", "quality_confidence")
    if direct:
        return direct
    channel = (_row_value(row, "channel") or "unknown").casefold()
    maturity = {
        "stable": "curated stable",
        "beta": "curated beta",
        "experimental": "experimental",
    }.get(channel, channel or "unknown")
    tiers = _row_value(row, "quality_tiers")
    return "{} ({})".format(maturity, tiers) if tiers else maturity


def input_roles(row: Mapping[str, object]) -> tuple[str, ...]:
    """Return normalized connector roles, always including the primary image."""
    roles = split_tags(_row_value(row, "input_roles", "inputs"))
    if not roles:
        try:
            count = int(_row_value(row, "input_count") or "1")
        except ValueError:
            count = 1
        roles = ("image",) if count <= 1 else ("image",) + tuple("input_{}".format(index) for index in range(2, count + 1))
    if "image" not in {role.casefold() for role in roles}:
        roles = ("image", *roles)
    return roles


def input_diagnostics(row: Mapping[str, object], available_inputs=("image",)) -> dict[str, object]:
    """Describe whether the selected effect's connector roles can be satisfied."""
    roles = input_roles(row)
    available = {value.casefold() for value in split_tags(available_inputs)}
    available.add("image")
    missing = tuple(role for role in roles if role.casefold() not in available)
    return {
        "count": len(roles),
        "roles": roles,
        "missing": missing,
        "ready": not missing,
        "label": "Ready" if not missing else "Needs {}".format(", ".join(missing)),
    }


def sort_catalog(rows, sort_by="name"):
    """Return a stable browser ordering by name, category, or declared GPU cost."""
    mode = _text(sort_by).casefold().replace(" ", "_")

    def identity(row):
        return (_row_value(row, "name") or _row_value(row, "id")).casefold()

    if mode in {"category", "category_name"}:
        key = lambda row: (_row_value(row, "category").casefold(), identity(row), _row_value(row, "id").casefold())
    elif mode in {"cost", "gpu_cost", "gpu"}:
        key = lambda row: (
            GPU_COST_ORDER.get(_row_value(row, "gpu_cost", "processing_gpu_cost").casefold(), GPU_COST_ORDER["unknown"]),
            identity(row),
            _row_value(row, "id").casefold(),
        )
    else:
        key = lambda row: (identity(row), _row_value(row, "id").casefold())
    return sorted((dict(row) for row in rows), key=key)


def display_row(row: Mapping[str, object], favorites=()) -> dict[str, str]:
    """Project arbitrary catalog columns into the browser's stable column set."""
    package_id = _row_value(row, "id")
    favorite_keys = {_text(item).casefold() for item in favorites}
    readiness = input_diagnostics(row, split_tags(_row_value(row, "available_inputs")) or ("image",))
    return {
        "id": package_id,
        "name": _row_value(row, "name") or package_id,
        "version": _row_value(row, "version"),
        "category": _row_value(row, "category"),
        "channel": _row_value(row, "channel") or "unknown",
        "description": _row_value(row, "description"),
        "tags": _row_value(row, "tags"),
        "favorite": "1" if package_id.casefold() in favorite_keys else "0",
        "preview": _row_value(row, "preview", "preview_path"),
        "input_count": _row_value(row, "input_count") or str(readiness["count"]),
        "input_roles": _row_value(row, "input_roles") or ", ".join(readiness["roles"]),
        "input_readiness": _row_value(row, "input_readiness") or str(readiness["label"]),
        "parameter_count": _row_value(row, "parameter_count") or "0",
        "parameters": _row_value(row, "parameters", "parameter_summary"),
        "alpha_policy": _row_value(row, "alpha_policy") or "unspecified",
        "resolution_policy": _row_value(row, "resolution_policy") or "unspecified",
        "image_contract": _row_value(row, "image_contract") or "legacy manifest contract",
        "compatibility": compatibility_label(row),
        "compatibility_confidence": compatibility_confidence_label(row),
        "quality": quality_label(row),
        "model": _row_value(row, "model", "processing_model") or "Unknown",
        "gpu_cost": _row_value(row, "gpu_cost", "processing_gpu_cost") or "Unknown",
        "capabilities": _row_value(row, "capabilities"),
        "component": _row_value(row, "component", "touchdesigner_component"),
    }


def filter_catalog(
    rows,
    search="",
    category="",
    tags=(),
    favorites=(),
    favorites_only=False,
    channel="",
    model="",
    capability="",
    input_readiness="",
    available_inputs=("image",),
    sort_by="name",
):
    """Filter catalog mappings without depending on TouchDesigner.

    Search terms are ANDed and matched across all visible metadata. Category and
    tag comparisons are case-insensitive; requested tags must all be present.
    """
    terms = tuple(part.casefold() for part in _text(search).split() if part)
    category_key = _text(category).casefold()
    if category_key in {"all", "*"}:
        category_key = ""
    wanted_tags = {tag.casefold() for tag in split_tags(tags)}
    favorite_keys = {_text(item).casefold() for item in (favorites or ())}
    channel_key = _text(channel).casefold()
    model_key = _text(model).casefold()
    capability_key = _text(capability).casefold()
    readiness_key = _text(input_readiness).casefold().replace(" ", "_")
    if channel_key in {"all", "*"}:
        channel_key = ""
    if model_key in {"all", "*"}:
        model_key = ""
    if capability_key in {"all", "*"}:
        capability_key = ""
    if readiness_key in {"all", "*"}:
        readiness_key = ""
    matches = []
    for source_row in rows:
        row = dict(source_row)
        package_id = _row_value(row, "id")
        row_category = _row_value(row, "category").casefold()
        row_tags = {tag.casefold() for tag in split_tags(_row_value(row, "tags"))}
        row_channel = _row_value(row, "channel").casefold()
        row_model = _row_value(row, "model", "processing_model").casefold()
        row_capabilities = {item.casefold() for item in split_tags(_row_value(row, "capabilities"))}
        diagnostics = input_diagnostics(row, available_inputs)
        haystack = " ".join(
            _row_value(row, name)
            for name in (
                "id", "name", "version", "kind", "category", "channel", "tags", "description",
                "model", "processing_model", "gpu_cost", "capabilities", "input_roles", "parameters",
                "alpha_policy", "resolution_policy", "image_contract", "compatibility",
            )
        ).casefold()
        if terms and not all(term in haystack for term in terms):
            continue
        if category_key and row_category != category_key:
            continue
        if wanted_tags and not wanted_tags.issubset(row_tags):
            continue
        if favorites_only and package_id.casefold() not in favorite_keys:
            continue
        if channel_key and row_channel != channel_key:
            continue
        if model_key and row_model != model_key:
            continue
        if capability_key and capability_key not in row_capabilities:
            continue
        if readiness_key in {"ready", "connected"} and not diagnostics["ready"]:
            continue
        if readiness_key in {"needs_aux", "missing", "not_ready"} and diagnostics["ready"]:
            continue
        if readiness_key == "image_only" and diagnostics["count"] != 1:
            continue
        matches.append(row)
    return sort_catalog(matches, sort_by)


def selected_details(row: Mapping[str, object], available_inputs=("image",)) -> tuple[tuple[str, str], ...]:
    """Build ordered, human-readable detail rows for the visual browser panel."""
    projected = display_row(row)
    diagnostics = input_diagnostics(row, available_inputs)
    inputs = "{}: {}".format(diagnostics["count"], ", ".join(diagnostics["roles"]))
    image_contract = "alpha={} | resolution={}".format(projected["alpha_policy"], projected["resolution_policy"])
    if projected["image_contract"] and projected["image_contract"] != "legacy manifest contract":
        image_contract += " | {}".format(projected["image_contract"])
    return (
        ("Effect", "{} {}".format(projected["name"], projected["version"]).strip()),
        ("ID", projected["id"]),
        ("Description", projected["description"] or "No description"),
        ("Category / Channel", "{} / {}".format(projected["category"], projected["channel"])),
        ("Processing", "{} | {} GPU | {}".format(projected["model"], projected["gpu_cost"], projected["capabilities"] or "no special capabilities")),
        ("Inputs", inputs),
        ("Input readiness", str(diagnostics["label"])),
        ("Parameters", "{} | {}".format(projected["parameter_count"], projected["parameters"] or "none")),
        ("Image contract", image_contract),
        ("Quality", projected["quality"]),
        ("Compatibility", "{} ({})".format(projected["compatibility"], projected["compatibility_confidence"])),
        ("Preview", projected["preview"] or "not available"),
    )


class ImageFXBrowserExt:
    """Extension promoted by an ImageFX Browser COMP."""

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self._catalog_rows = []
        self._filtered_rows = []
        self.LastError = ""

    def _parameter(self, name):
        collection = getattr(self.ownerComp, "par", None)
        if collection is None:
            return None
        try:
            return collection[name]
        except (KeyError, TypeError, AttributeError):
            return getattr(collection, name, None)

    def _parameter_value(self, name, default=""):
        parameter = self._parameter(name)
        if parameter is None:
            return default
        try:
            return parameter.eval()
        except AttributeError:
            return parameter

    def _set_parameter(self, name, value) -> bool:
        parameter = self._parameter(name)
        if parameter is None:
            return False
        if hasattr(parameter, "val"):
            parameter.val = value
        elif hasattr(parameter, "value"):
            parameter.value = value
        elif hasattr(parameter, "set"):
            parameter.set(value)
        else:
            try:
                setattr(self.ownerComp.par, name, value)
            except (AttributeError, TypeError):
                return False
        return True

    def _set_status(self, message, error=False):
        self.LastError = _text(message) if error else ""
        prefix = "Error: " if error else ""
        self._set_parameter("Status", prefix + _text(message))

    def _library(self):
        candidates = []
        parent_method = getattr(self.ownerComp, "parent", None)
        if callable(parent_method):
            try:
                candidates.append(parent_method())
            except Exception:
                pass
        owner_op = getattr(self.ownerComp, "op", None)
        if callable(owner_op):
            for path in ("..", "../.."):
                try:
                    candidates.append(owner_op(path))
                except Exception:
                    pass
        for candidate in candidates:
            if candidate is not None and hasattr(candidate, "RefreshCatalog") and hasattr(candidate, "CreateEffect"):
                return candidate
        raise RuntimeError("parent ImageFX Library extension is unavailable")

    def _catalog(self, library=None):
        library = library or self._library()
        library_op = getattr(library, "op", None)
        if callable(library_op):
            table = library_op("catalog")
            if table is not None:
                return table
        owner_op = getattr(self.ownerComp, "op", None)
        if callable(owner_op):
            for path in ("../catalog", "catalog"):
                table = owner_op(path)
                if table is not None:
                    return table
        raise RuntimeError("library catalog DAT is missing")

    def _results_table(self):
        owner_op = getattr(self.ownerComp, "op", None)
        if not callable(owner_op):
            raise RuntimeError("browser results DAT is unavailable")
        table = owner_op("results") or owner_op("browser_results")
        if table is None:
            raise RuntimeError("browser results DAT is missing")
        return table

    def _optional_op(self, *names):
        owner_op = getattr(self.ownerComp, "op", None)
        if not callable(owner_op):
            return None
        for name in names:
            try:
                operator = owner_op(name)
            except Exception:
                operator = None
            if operator is not None:
                return operator
        return None

    def _available_inputs(self):
        values = split_tags(self._parameter_value("Availableinputs", "image"))
        return values or ("image",)

    def _write_results(self, rows, favorites):
        table = self._results_table()
        table.setSize(0, 0)
        table.appendRow(RESULT_COLUMNS)
        for row in rows:
            projected = display_row(row, favorites)
            diagnostics = input_diagnostics(row, self._available_inputs())
            projected["input_readiness"] = str(diagnostics["label"])
            table.appendRow(tuple(projected[column] for column in RESULT_COLUMNS))
        text_dat = self._optional_op("results_text")
        if text_dat is not None:
            visible = []
            for index, row in enumerate(rows[:MAX_VISIBLE_RESULTS], start=1):
                projected = display_row(row, favorites)
                marker = "*" if projected["favorite"] == "1" else " "
                visible.append(
                    "{:>2}.{} {}  [{} / {} GPU]".format(
                        index, marker, projected["name"], projected["category"], projected["gpu_cost"]
                    )
                )
            if len(rows) > MAX_VISIBLE_RESULTS:
                visible.append("... {} more results".format(len(rows) - MAX_VISIBLE_RESULTS))
            text_dat.text = "\n".join(visible) if visible else "No effects match the current filters."

    def _favorites(self):
        return parse_favorites(self._parameter_value("Favorites", "[]"))

    def _selected_id(self):
        for name in ("Selectedid", "Selectedeffect", "Selected"):
            value = _text(self._parameter_value(name, ""))
            if value:
                return value
        return ""

    def _reload_selected_preview(self):
        preview = self._optional_op("selected_preview")
        if preview is None:
            return False
        parameter = preview.par["reload"]
        if parameter is not None:
            parameter.pulse()
        cook = getattr(preview, "cook", None)
        if callable(cook):
            cook(force=True)
        return True

    def _resolve_target(self, target=None):
        target = target if target is not None else self._parameter_value("Target", None)
        if target is None or _text(target) == "":
            return None
        if not isinstance(target, str):
            return target
        owner_op = getattr(self.ownerComp, "op", None)
        if callable(owner_op):
            resolved = owner_op(target)
            if resolved is not None:
                return resolved
        global_op = globals().get("op")
        if callable(global_op):
            return global_op(target)
        return None

    def LoadCatalog(self):
        """Load rows from the parent library's catalog DAT."""
        self._catalog_rows = catalog_rows(self._catalog())
        return list(self._catalog_rows)

    def ApplyFilters(self, rows=None):
        """Apply current COMP parameters and rewrite the ``results`` DAT."""
        try:
            source_rows = list(rows) if rows is not None else (self._catalog_rows or self.LoadCatalog())
            favorites = self._favorites()
            self._filtered_rows = filter_catalog(
                source_rows,
                search=self._parameter_value("Search", ""),
                category=self._parameter_value("Category", ""),
                tags=self._parameter_value("Tags", ""),
                favorites=favorites,
                favorites_only=bool(self._parameter_value("Favoritesonly", False)),
                channel=self._parameter_value("Channel", ""),
                model=self._parameter_value("Model", ""),
                capability=self._parameter_value("Capability", ""),
                input_readiness=self._parameter_value("Inputreadiness", ""),
                available_inputs=self._available_inputs(),
                sort_by=self._parameter_value("Sortby", "name"),
            )
            self._write_results(self._filtered_rows, favorites)
            self.UpdateSelection(set_status=False)
            self._set_status("{} of {} effects".format(len(self._filtered_rows), len(source_rows)))
            return list(self._filtered_rows)
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return []

    def Refresh(self):
        """Refresh the parent catalog, reload it, and reapply browser filters."""
        try:
            library = self._library()
            library.RefreshCatalog()
            self._catalog_rows = catalog_rows(self._catalog(library))
            return self.ApplyFilters(self._catalog_rows)
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return []

    def SetSelected(self, package_id):
        package_id = _text(package_id)
        if not package_id:
            self._set_status("No effect selected", error=True)
            return False
        for name in ("Selectedid", "Selectedeffect", "Selected"):
            if self._set_parameter(name, package_id):
                self.UpdateSelection(package_id, set_status=False)
                self._set_status("Selected {}".format(package_id))
                return True
        self._set_status("Selected effect parameter is missing", error=True)
        return False

    def UpdateSelection(self, package_id=None, set_status=True):
        """Populate selected preview and diagnostics without creating an effect."""
        try:
            rows = self._catalog_rows or self.LoadCatalog()
            selected_id = _text(package_id or self._selected_id())
            if not selected_id and rows:
                selected_id = _row_value(rows[0], "id")
                self._set_parameter("Selectedid", selected_id)
            selected = next(
                (row for row in rows if _row_value(row, "id").casefold() == selected_id.casefold()),
                None,
            )
            if selected is None:
                if set_status:
                    self._set_status("Selected effect is not in the catalog", error=True)
                return None
            details = selected_details(selected, self._available_inputs())
            projected = display_row(selected, self._favorites())
            self._set_parameter("Selectedpreview", projected["preview"])
            self._reload_selected_preview()
            detail_text = "\n\n".join("{}\n{}".format(label, value) for label, value in details)
            self._set_parameter("Selecteddiagnostics", detail_text)

            table = self._optional_op("selected_details", "details")
            if table is not None:
                table.setSize(0, 0)
                table.appendRow(("field", "value"))
                for detail in details:
                    table.appendRow(detail)
            text_dat = self._optional_op("selected_detail_text", "detail_text")
            if text_dat is not None:
                text_dat.text = detail_text
            if set_status:
                self._set_status("Selected {}".format(selected_id))
            return dict(details)
        except Exception as exc:
            if set_status:
                self._set_status(str(exc), error=True)
            return None

    def SelectedDiagnostics(self):
        """Return structured diagnostics for scripting and rack preparation."""
        selected_id = self._selected_id()
        rows = self._catalog_rows or self.LoadCatalog()
        selected = next(
            (row for row in rows if _row_value(row, "id").casefold() == selected_id.casefold()),
            None,
        )
        if selected is None:
            return {}
        result = dict(selected_details(selected, self._available_inputs()))
        result["input_diagnostics"] = input_diagnostics(selected, self._available_inputs())
        return result

    def PreviewPath(self):
        """Return the selected preview path resolved against the library checkout."""
        relative = _text(self._parameter_value("Selectedpreview", ""))
        if not relative:
            return ""
        if os.path.isabs(relative):
            return os.path.normpath(relative)
        root = _text(self._parameter_value("Rootfolder", ""))
        if not root:
            project_object = globals().get("project")
            root = _text(getattr(project_object, "folder", ""))
        return os.path.normpath(os.path.join(root or os.getcwd(), relative))

    def ToggleFavorite(self, package_id=None):
        """Toggle the selected package in the JSON-backed favorite set."""
        package_id = _text(package_id or self._selected_id())
        if not package_id:
            self._set_status("No effect selected", error=True)
            return False
        favorites = self._favorites()
        existing = next((item for item in favorites if item.casefold() == package_id.casefold()), None)
        if existing is None:
            favorites.add(package_id)
            message = "Added {} to favorites".format(package_id)
        else:
            favorites.remove(existing)
            message = "Removed {} from favorites".format(package_id)
        if not self._set_parameter("Favorites", serialize_favorites(favorites)):
            self._set_status("Favorites parameter is missing", error=True)
            return False
        self.ApplyFilters()
        self._set_status(message)
        return existing is None

    def CreateSelected(self, target=None):
        """Create the selected package in ``Target`` via the library extension."""
        package_id = self._selected_id()
        if not package_id:
            self._set_status("No effect selected", error=True)
            return None
        resolved_target = self._resolve_target(target)
        if resolved_target is None:
            self._set_status("Target COMP is not set or cannot be resolved", error=True)
            return None
        try:
            instance = self._library().CreateEffect(package_id, target=resolved_target)
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return None
        label = _text(getattr(instance, "path", "")) or _text(getattr(instance, "name", "")) or package_id
        self._set_status("Created {}".format(label))
        return instance
