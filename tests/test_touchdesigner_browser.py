from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BROWSER = _load_module(
    "tdimagefx_touchdesigner_browser",
    Path("touchdesigner") / "extensions" / "ImageFXBrowserExt.py",
)
CALLBACKS = _load_module(
    "tdimagefx_touchdesigner_browser_callbacks",
    Path("touchdesigner") / "callbacks" / "browser_parameter_callbacks.py",
)


class FakeParameter:
    def __init__(self, value=""):
        self.val = value

    def eval(self):
        return self.val


class FakeParameters:
    def __init__(self, **values):
        self._parameters = {name: FakeParameter(value) for name, value in values.items()}

    def __getitem__(self, name):
        return self._parameters.get(name)

    def __getattr__(self, name):
        try:
            return self._parameters[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class FakeTable:
    def __init__(self, rows=()):
        self.data = [list(row) for row in rows]

    def rows(self):
        return [list(row) for row in self.data]

    def setSize(self, rows, columns):
        self.data = []

    def appendRow(self, values):
        self.data.append([str(value) for value in values])


class FakeInstance:
    path = "/project1/target/new_effect"


class FakeLibrary:
    def __init__(self, catalog):
        self.catalog = catalog
        self.refresh_count = 0
        self.created = []

    def op(self, name):
        return self.catalog if name == "catalog" else None

    def RefreshCatalog(self):
        self.refresh_count += 1
        return max(len(self.catalog.data) - 1, 0)

    def CreateEffect(self, package_id, target=None):
        self.created.append((package_id, target))
        return FakeInstance()


class FakeOwner:
    def __init__(self, library, **parameters):
        defaults = {
            "Search": "",
            "Category": "",
            "Channel": "",
            "Model": "",
            "Capability": "",
            "Inputreadiness": "",
            "Availableinputs": "image",
            "Sortby": "name",
            "Tags": "",
            "Favorites": "[]",
            "Favoritesonly": False,
            "Selectedid": "",
            "Selectedpreview": "",
            "Selecteddiagnostics": "",
            "Target": None,
            "Status": "",
        }
        defaults.update(parameters)
        self.par = FakeParameters(**defaults)
        self.library = library
        self.results = FakeTable()
        self.named_ops = {}

    def parent(self):
        return self.library

    def op(self, name):
        if name == "results":
            return self.results
        return self.named_ops.get(name)


CATALOG_ROWS = (
    (
        "id", "name", "version", "category", "channel", "description", "tags", "compatibility",
        "compatibility_confidence", "processing_model", "gpu_cost", "capabilities", "preview",
        "input_count", "input_roles", "parameter_count", "parameters", "alpha_policy",
        "resolution_policy", "image_contract", "component",
    ),
    (
        "tdimagefx.color.grade", "Film Grade", "1.0.0", "color", "stable", "Warm film color grade.",
        "grading, warm", "TD 2022.2+", "runtime verified", "single_pass", "low", "",
        "docs/gallery/grade.png", "1", "image", "2", "Mix (float); Warmth (float)", "preserve",
        "input", "legacy manifest contract", "tox/grade.tox",
    ),
    (
        "tdimagefx.stylize.vhs", "VHS Tape", "1.0.0", "stylize", "experimental", "Analog tape damage.",
        "analog, animated, tape", "TD 2022.2+", "declared", "temporal", "medium", "history, animated",
        "docs/gallery/vhs.png", "2", "image, flow", "3", "Mix (float); Time (float); Noise (float)",
        "preserve", "input", "color source>linear>source", "tox/vhs.tox",
    ),
)


class BrowserPureFunctionTests(unittest.TestCase):
    def test_favorites_are_defensive_and_deterministic(self):
        self.assertEqual(BROWSER.parse_favorites("not json"), set())
        self.assertEqual(BROWSER.parse_favorites('{"id":"wrong-shape"}'), set())
        self.assertEqual(BROWSER.parse_favorites('["fx.B", "fx.a", "fx.B", 4]'), {"fx.B", "fx.a"})
        self.assertEqual(BROWSER.serialize_favorites({"fx.B", "fx.a"}), '["fx.a","fx.B"]')

    def test_filtering_is_case_insensitive_and_ands_tags(self):
        rows = BROWSER.catalog_rows(FakeTable(CATALOG_ROWS))
        matches = BROWSER.filter_catalog(rows, search="vHs ANIMATED", category="STYLIZE", tags="TAPE, analog")
        self.assertEqual([row["id"] for row in matches], ["tdimagefx.stylize.vhs"])
        self.assertEqual(BROWSER.filter_catalog(rows, tags="tape, missing"), [])

    def test_favorites_only_filter_ignores_id_case(self):
        rows = BROWSER.catalog_rows(FakeTable(CATALOG_ROWS))
        matches = BROWSER.filter_catalog(rows, favorites={"TDIMAGEFX.COLOR.GRADE"}, favorites_only=True)
        self.assertEqual([row["id"] for row in matches], ["tdimagefx.color.grade"])

    def test_display_projection_has_required_metadata_columns(self):
        source = {
            "id": "fx.example",
            "name": "Example",
            "td_min_build": "2023.1",
            "os": "windows, macos",
            "processing_model": "multi_pass",
            "processing_gpu_cost": "high",
        }
        projected = BROWSER.display_row(source, {"FX.EXAMPLE"})
        self.assertEqual(tuple(projected), BROWSER.RESULT_COLUMNS)
        self.assertEqual(projected["compatibility"], "TD 2023.1+ | windows, macos")
        self.assertEqual(projected["model"], "multi_pass")
        self.assertEqual(projected["gpu_cost"], "high")
        self.assertEqual(projected["favorite"], "1")
        self.assertEqual(projected["input_count"], "1")
        self.assertEqual(projected["compatibility_confidence"], "declared")

    def test_filters_channel_model_capability_and_input_readiness(self):
        rows = BROWSER.catalog_rows(FakeTable(CATALOG_ROWS))
        matches = BROWSER.filter_catalog(
            rows,
            channel="experimental",
            model="temporal",
            capability="history",
            input_readiness="needs_aux",
            available_inputs="image",
        )
        self.assertEqual([row["id"] for row in matches], ["tdimagefx.stylize.vhs"])
        self.assertEqual(
            [row["id"] for row in BROWSER.filter_catalog(rows, input_readiness="ready", available_inputs="image")],
            ["tdimagefx.color.grade"],
        )
        self.assertEqual(
            [row["id"] for row in BROWSER.filter_catalog(rows, input_readiness="ready", available_inputs="image, flow")],
            ["tdimagefx.color.grade", "tdimagefx.stylize.vhs"],
        )

    def test_sorting_and_selected_details_expose_production_diagnostics(self):
        rows = BROWSER.catalog_rows(FakeTable(CATALOG_ROWS))
        self.assertEqual(
            [row["id"] for row in BROWSER.sort_catalog(reversed(rows), "cost")],
            ["tdimagefx.color.grade", "tdimagefx.stylize.vhs"],
        )
        details = dict(BROWSER.selected_details(rows[1], available_inputs="image"))
        self.assertEqual(details["Input readiness"], "Needs flow")
        self.assertIn("preserve", details["Image contract"])
        self.assertIn("declared", details["Compatibility"])


class BrowserExtensionTests(unittest.TestCase):
    def make_browser(self, **parameters):
        library = FakeLibrary(FakeTable(CATALOG_ROWS))
        owner = FakeOwner(library, **parameters)
        return BROWSER.ImageFXBrowserExt(owner), owner, library

    def test_refresh_delegates_to_library_and_populates_results(self):
        browser, owner, library = self.make_browser(Category="COLOR", Favorites='["tdimagefx.color.grade"]')
        rows = browser.Refresh()
        self.assertEqual(library.refresh_count, 1)
        self.assertEqual([row["id"] for row in rows], ["tdimagefx.color.grade"])
        self.assertEqual(tuple(owner.results.data[0]), BROWSER.RESULT_COLUMNS)
        favorite_index = BROWSER.RESULT_COLUMNS.index("favorite")
        self.assertEqual(owner.results.data[1][favorite_index], "1")
        self.assertEqual(owner.par.Status.eval(), "1 of 2 effects")

    def test_toggle_favorite_persists_json_and_updates_results(self):
        browser, owner, _ = self.make_browser(Selectedid="tdimagefx.stylize.vhs")
        browser.Refresh()
        self.assertTrue(browser.ToggleFavorite())
        self.assertEqual(owner.par.Favorites.eval(), '["tdimagefx.stylize.vhs"]')
        self.assertIn("Added", owner.par.Status.eval())
        self.assertFalse(browser.ToggleFavorite())
        self.assertEqual(owner.par.Favorites.eval(), "[]")

    def test_create_selected_uses_parent_library_and_explicit_target(self):
        target = object()
        browser, owner, library = self.make_browser(Selectedid="tdimagefx.color.grade", Target=target)
        instance = browser.CreateSelected()
        self.assertIsInstance(instance, FakeInstance)
        self.assertEqual(library.created, [("tdimagefx.color.grade", target)])
        self.assertEqual(owner.par.Status.eval(), "Created /project1/target/new_effect")

    def test_create_selected_reports_missing_target_without_calling_library(self):
        browser, owner, library = self.make_browser(Selectedid="tdimagefx.color.grade", Target=None)
        self.assertIsNone(browser.CreateSelected())
        self.assertEqual(library.created, [])
        self.assertIn("Error: Target COMP", owner.par.Status.eval())

    def test_selection_updates_preview_and_structured_diagnostics(self):
        browser, owner, _ = self.make_browser(Selectedid="tdimagefx.stylize.vhs")
        browser.LoadCatalog()
        details = browser.UpdateSelection()
        self.assertEqual(owner.par.Selectedpreview.eval(), "docs/gallery/vhs.png")
        self.assertIn("Needs flow", owner.par.Selecteddiagnostics.eval())
        self.assertEqual(details["Input readiness"], "Needs flow")
        diagnostics = browser.SelectedDiagnostics()
        self.assertFalse(diagnostics["input_diagnostics"]["ready"])


class BrowserCallbackTests(unittest.TestCase):
    def test_callbacks_route_filter_and_pulse_actions(self):
        calls = []

        class Browser:
            def ApplyFilters(self):
                calls.append("ApplyFilters")

            def UpdateSelection(self):
                calls.append("UpdateSelection")

            def Refresh(self):
                calls.append("Refresh")

            def CreateSelected(self):
                calls.append("CreateSelected")

            def ToggleFavorite(self):
                calls.append("ToggleFavorite")

        class Parameter:
            def __init__(self, name):
                self.name = name

        original_parent = getattr(CALLBACKS, "parent", None)
        CALLBACKS.parent = lambda: Browser()
        try:
            CALLBACKS.onValueChange(Parameter("Search"), None)
            CALLBACKS.onValueChange(Parameter("Channel"), None)
            CALLBACKS.onValueChange(Parameter("Selectedid"), None)
            CALLBACKS.onPulse(Parameter("Refresh"))
            CALLBACKS.onPulse(Parameter("Create"))
            CALLBACKS.onPulse(Parameter("ToggleFavorite"))
        finally:
            if original_parent is None:
                del CALLBACKS.parent
            else:
                CALLBACKS.parent = original_parent
        self.assertEqual(
            calls,
            ["ApplyFilters", "ApplyFilters", "UpdateSelection", "Refresh", "CreateSelected", "ToggleFavorite"],
        )


if __name__ == "__main__":
    unittest.main()
