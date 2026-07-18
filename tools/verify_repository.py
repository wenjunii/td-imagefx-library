"""Run the repository checks used locally and by GitHub Actions.

This script has no third-party dependencies. Run it from any working directory:

    python tools/verify_repository.py
"""

from __future__ import annotations

import ast
import json
import hashlib
import math
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Friendly error from main() on Python 3.10 and older.
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PACKAGE_ROOT = ROOT / "packages"
PUBLIC_FEED = ROOT / "registry" / "update-feed.json"
LOCAL_FEED = ROOT / "registry" / "update-feed.local.json"
EMBODY_INTEGRATION = ROOT / "integrations" / "embody"
EXPECTED_EFFECT_ID_COUNT = 96
EXPECTED_PACKAGE_VERSION_COUNT = 122
PUBLIC_FEED_URL = (
    "https://raw.githubusercontent.com/wenjunii/td-imagefx-library/"
    "main/registry/update-feed.json"
)

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tdimagefx import Version, load_manifest  # noqa: E402
from tdimagefx.errors import ImageFxError, SecurityError  # noqa: E402
from tdimagefx.paths import validate_package_path  # noqa: E402


class VerificationError(RuntimeError):
    """A repository invariant failed."""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VerificationError(f"Cannot read JSON from {path.relative_to(ROOT)}: {exc}") from exc


def _extract_assignment(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    if match is None:
        raise VerificationError(f"Cannot find {name} in {path.relative_to(ROOT)}")
    return match.group(1)


def _source_test_count() -> int:
    """Count checked-in unittest methods without importing the test modules."""

    count = 0
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            raise VerificationError(
                f"Cannot inspect tests in {path.relative_to(ROOT)}: {exc}"
            ) from exc
        count += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    if count < 1:
        raise VerificationError("No source unit tests were discovered")
    return count


def _check_public_documentation() -> None:
    """Keep public verification claims synchronized with checked source data."""

    readme_path = ROOT / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(f"Cannot read README.md: {exc}") from exc

    catalog_claim = re.search(
        r"validated all (\d+) current effects with (\d+) versioned effect",
        readme,
    )
    coverage_claim = re.search(
        r"(\d+) previews, (\d+) visual baselines, and (\d+) benchmark samples",
        readme,
    )
    test_claim = re.search(
        r"fresh repository run completed (\d+) tests successfully",
        readme,
        re.IGNORECASE,
    )
    if (
        catalog_claim is None
        or tuple(map(int, catalog_claim.groups()))
        != (EXPECTED_EFFECT_ID_COUNT, EXPECTED_PACKAGE_VERSION_COUNT)
    ):
        raise VerificationError("README catalog counts do not match the repository")
    if (
        coverage_claim is None
        or tuple(map(int, coverage_claim.groups()))
        != (EXPECTED_EFFECT_ID_COUNT,) * 3
    ):
        raise VerificationError("README generated-coverage counts do not match the catalog")
    source_test_count = _source_test_count()
    if test_claim is None or int(test_claim.group(1)) != source_test_count:
        raise VerificationError(
            "README test count does not match the checked-in suite "
            f"({source_test_count})"
        )
    for reference in (
        "docs/embody-envoy-integration.md",
        "integrations/embody/",
    ):
        if reference not in readme:
            raise VerificationError(
                f"README is missing the public integration reference: {reference}"
            )


def _check_versions() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    versions = {
        "pyproject.toml": str(project["version"]),
        "src/tdimagefx/__init__.py": _extract_assignment(ROOT / "src" / "tdimagefx" / "__init__.py", "__version__"),
        "touchdesigner/scripts/build_project.py": _extract_assignment(
            ROOT / "touchdesigner" / "scripts" / "build_project.py", "LIBRARY_VERSION"
        ),
    }
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{path}={version}" for path, version in versions.items())
        raise VerificationError(f"Library version mismatch: {details}")
    return next(iter(versions.values()))


def _require_package_file(
    package_dir: Path,
    relative_path: str,
    *,
    label: str,
    manifest_path: Path,
) -> Path:
    try:
        safe_path = validate_package_path(relative_path, label=label)
    except SecurityError as exc:
        raise VerificationError(f"{manifest_path.relative_to(ROOT)}: {exc}") from exc
    candidate = package_dir.joinpath(*safe_path.parts).resolve()
    try:
        candidate.relative_to(package_dir)
    except ValueError as exc:
        raise VerificationError(
            f"{label} escapes its package: {manifest_path.relative_to(ROOT)} -> {relative_path}"
        ) from exc
    if not candidate.is_file():
        raise VerificationError(f"Missing {label}: {candidate.relative_to(ROOT)}")
    return candidate


def _check_manifests() -> tuple[int, set[str], dict[str, str]]:
    manifest_paths = sorted(PACKAGE_ROOT.glob("*/*/package.json"))
    if not manifest_paths:
        raise VerificationError("No package manifests found")

    seen: set[tuple[str, str]] = set()
    package_ids: set[str] = set()
    latest: dict[str, Version] = {}
    for manifest_path in manifest_paths:
        try:
            manifest = load_manifest(manifest_path)
        except ImageFxError as exc:
            raise VerificationError(
                f"Invalid package manifest {manifest_path.relative_to(ROOT)}: {exc}"
            ) from exc
        package_id = manifest.id
        version = str(manifest.version)
        identity = (package_id, version)
        if identity in seen:
            raise VerificationError(f"Duplicate package identity: {package_id}@{version}")
        seen.add(identity)
        package_ids.add(package_id)
        current = latest.get(package_id)
        if (
            current is not None
            and manifest.version == current
            and not manifest.version.exactly_equals(current)
        ):
            raise VerificationError(
                f"Ambiguous versions with equal SemVer precedence for {package_id}: "
                f"{current} and {manifest.version}"
            )
        if current is None or current < manifest.version:
            latest[package_id] = manifest.version

        package_dir = manifest_path.parent.resolve()
        try:
            package_dir.relative_to(PACKAGE_ROOT.resolve())
        except ValueError as exc:
            raise VerificationError(
                f"Package directory escapes packages/: {manifest_path.relative_to(ROOT)}"
            ) from exc
        expected_dir = (PACKAGE_ROOT / package_id / version).resolve()
        if package_dir != expected_dir:
            raise VerificationError(
                f"Package path mismatch for {package_id}@{version}: "
                f"expected {expected_dir.relative_to(ROOT)}, found {package_dir.relative_to(ROOT)}"
            )

        for entrypoint_name, relative_path in manifest.entrypoints.items():
            if relative_path is None:
                continue
            _require_package_file(
                package_dir,
                relative_path,
                label=f"{entrypoint_name} entrypoint",
                manifest_path=manifest_path,
            )

        passes = manifest.processing.get("passes")
        if passes is not None:
            for index, relative_path in enumerate(passes):
                _require_package_file(
                    package_dir,
                    relative_path,
                    label=f"processing pass {index + 1}",
                    manifest_path=manifest_path,
                )

    if (
        len(manifest_paths) != EXPECTED_PACKAGE_VERSION_COUNT
        or len(package_ids) != EXPECTED_EFFECT_ID_COUNT
    ):
        raise VerificationError(
            "Completed v0.3 catalog must contain exactly "
            f"{EXPECTED_EFFECT_ID_COUNT} effect IDs and {EXPECTED_PACKAGE_VERSION_COUNT} immutable versions; "
            f"found {len(manifest_paths)} manifests for {len(package_ids)} effect IDs"
        )

    required_native_assets = (
        ROOT / "TD_ImageFX_Library.toe",
        ROOT / "touchdesigner" / "core" / "TDImageFXLibrary.tox",
        ROOT / "touchdesigner" / "core" / "FxBrowser.tox",
        ROOT / "touchdesigner" / "core" / "FxRack.tox",
        ROOT / "touchdesigner" / "core" / "ParticleRandomMove.tox",
        ROOT / "touchdesigner" / "core" / "FxUpdater.tox",
    )
    missing = [path.relative_to(ROOT) for path in required_native_assets if not path.is_file()]
    if missing:
        raise VerificationError("Missing native assets: " + ", ".join(map(str, missing)))
    return len(manifest_paths), package_ids, {
        package_id: str(version) for package_id, version in latest.items()
    }


def _item_ids(items: object, *, label: str) -> list[str]:
    if not isinstance(items, list):
        raise VerificationError(f"{label} must be a list")
    identifiers: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise VerificationError(f"{label}[{index}] must contain a non-empty id")
        identifiers.append(item["id"])
    if len(identifiers) != len(set(identifiers)):
        raise VerificationError(f"{label} contains duplicate package ids")
    return identifiers


def _check_generated_artifacts(package_ids: set[str], latest_versions: dict[str, str]) -> None:
    generated_files = (
        ROOT / "docs" / "gallery.md",
        ROOT / "docs" / "gallery.json",
        ROOT / "docs" / "gallery-baselines.json",
        ROOT / "docs" / "benchmark-data.json",
        ROOT / "docs" / "benchmarks.md",
    )
    missing = [path.relative_to(ROOT) for path in generated_files if not path.is_file()]
    if missing:
        raise VerificationError("Missing generated documentation: " + ", ".join(map(str, missing)))

    gallery = _read_json(ROOT / "docs" / "gallery.json")
    if gallery.get("schema_version") != 1:
        raise VerificationError("docs/gallery.json must use schema_version 1")
    gallery_ids = _item_ids(gallery.get("effects"), label="docs/gallery.json effects")
    if set(gallery_ids) != package_ids or len(gallery_ids) != EXPECTED_EFFECT_ID_COUNT:
        raise VerificationError("docs/gallery.json must contain every catalog package exactly once")
    gallery_versions = {
        item.get("id"): item.get("version")
        for item in gallery.get("effects", [])
        if isinstance(item, dict)
    }
    if gallery_versions != latest_versions:
        raise VerificationError("docs/gallery.json must describe the latest version of every effect")

    expected_previews = {f"{package_id}.png" for package_id in package_ids}
    gallery_dir = ROOT / "docs" / "gallery"
    actual_previews = {path.name for path in gallery_dir.glob("*.png") if path.is_file()}
    if actual_previews != expected_previews:
        missing_previews = sorted(expected_previews - actual_previews)
        extra_previews = sorted(actual_previews - expected_previews)
        raise VerificationError(
            f"Gallery previews do not match catalog: missing={missing_previews}, extra={extra_previews}"
        )

    baselines = _read_json(ROOT / "docs" / "gallery-baselines.json")
    images = baselines.get("images")
    if (
        baselines.get("schema_version") != 1
        or baselines.get("algorithm") != "sha256"
        or not isinstance(images, dict)
        or set(images) != expected_previews
        or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in images.values()
        )
    ):
        raise VerificationError("docs/gallery-baselines.json must contain one SHA-256 baseline per preview")

    benchmark_data = _read_json(ROOT / "docs" / "benchmark-data.json")
    if benchmark_data.get("schema_version") != 1:
        raise VerificationError("docs/benchmark-data.json must use schema_version 1")
    benchmark_ids = _item_ids(benchmark_data.get("samples"), label="docs/benchmark-data.json samples")
    if set(benchmark_ids) != package_ids or len(benchmark_ids) != EXPECTED_EFFECT_ID_COUNT:
        raise VerificationError("docs/benchmark-data.json must contain one unique sample per catalog package")
    benchmark_versions = {
        item.get("id"): item.get("version")
        for item in benchmark_data.get("samples", [])
        if isinstance(item, dict)
    }
    if benchmark_versions != latest_versions:
        raise VerificationError("docs/benchmark-data.json must measure the latest version of every effect")
    measured = False
    for index, sample in enumerate(benchmark_data["samples"]):
        gpu_ms = sample.get("gpu_ms")
        cpu_ms = sample.get("cpu_submission_ms")
        memory = sample.get("gpu_memory_bytes")
        passes = sample.get("passes")
        if gpu_ms is not None and (
            isinstance(gpu_ms, bool) or not isinstance(gpu_ms, (int, float))
            or not math.isfinite(gpu_ms) or gpu_ms < 0
        ):
            raise VerificationError(f"benchmark sample {index} has invalid gpu_ms")
        if (
            isinstance(cpu_ms, bool) or not isinstance(cpu_ms, (int, float))
            or not math.isfinite(cpu_ms) or cpu_ms < 0
        ):
            raise VerificationError(f"benchmark sample {index} has invalid cpu_submission_ms")
        if isinstance(memory, bool) or not isinstance(memory, int) or memory < 0:
            raise VerificationError(f"benchmark sample {index} has invalid gpu_memory_bytes")
        if isinstance(passes, bool) or not isinstance(passes, int) or passes < 1:
            raise VerificationError(f"benchmark sample {index} has invalid pass count")
        measured = measured or gpu_ms is not None or cpu_ms > 0 or memory > 0
    if not measured:
        raise VerificationError("benchmark data contains no runtime measurement")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_native_artifact(relative: str) -> Path:
    """Resolve a recorded native artifact without ever accepting a symlink."""

    unresolved = ROOT.joinpath(*Path(relative).parts)
    cursor = ROOT
    for part in Path(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise VerificationError(
                f"Native validation artifact is missing or unsafe: {relative}"
            )
    try:
        path = unresolved.resolve(strict=True)
        path.relative_to(ROOT.resolve())
    except (OSError, ValueError) as exc:
        raise VerificationError(
            f"Native validation artifact is missing or unsafe: {relative}"
        ) from exc
    if not path.is_file():
        raise VerificationError(f"Native validation artifact is missing or unsafe: {relative}")
    return path


def _check_native_validation(library_version: str) -> None:
    record = _read_json(ROOT / "docs" / "native-validation.json")
    if record.get("schema_version") != 1 or record.get("library_version") != library_version:
        raise VerificationError("docs/native-validation.json has an incompatible schema or library version")
    if record.get("catalog") != {
        "current_effects": EXPECTED_EFFECT_ID_COUNT,
        "package_versions": EXPECTED_PACKAGE_VERSION_COUNT,
    }:
        raise VerificationError("Native validation catalog counts do not match the repository")
    if record.get("results") != {
        "builder_errors": 0,
        "shader_errors": 0,
        "preview_errors": 0,
    }:
        raise VerificationError("Native validation does not record a clean TouchDesigner build")
    builder = record.get("builder")
    builder_relative = "touchdesigner/scripts/build_project.py"
    builder_path = ROOT / builder_relative
    if (
        not isinstance(builder, dict)
        or builder.get("path") != builder_relative
        or builder.get("sha256") != _sha256(builder_path)
    ):
        raise VerificationError("Native validation is not bound to the current builder source")
    environment = record.get("touchdesigner")
    if not isinstance(environment, dict) or any(
        not isinstance(environment.get(field), str) or not environment[field].strip()
        for field in ("version", "build", "os", "architecture")
    ):
        raise VerificationError("Native validation must name its TouchDesigner environment")

    expected_paths = {
        "TD_ImageFX_Library.toe",
        "touchdesigner/core/TDImageFXLibrary.tox",
        "touchdesigner/core/FxBrowser.tox",
        "touchdesigner/core/FxRack.tox",
        "touchdesigner/core/ParticleRandomMove.tox",
        "touchdesigner/core/FxUpdater.tox",
        *(
            path.relative_to(ROOT).as_posix()
            for path in sorted(PACKAGE_ROOT.glob("*/*/tox/*.tox"))
        ),
    }
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list):
        raise VerificationError("Native validation artifacts must be a list")
    recorded_paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise VerificationError(f"Native validation artifact {index} must be an object")
        relative = artifact.get("path")
        size = artifact.get("bytes")
        digest = artifact.get("sha256")
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise VerificationError(f"Native validation artifact {index} has an unsafe path")
        if relative in recorded_paths:
            raise VerificationError(f"Native validation contains duplicate artifact {relative}")
        recorded_paths.add(relative)
        path = _resolve_native_artifact(relative)
        if isinstance(size, bool) or not isinstance(size, int) or size != path.stat().st_size:
            raise VerificationError(f"Native validation size mismatch: {relative}")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise VerificationError(f"Native validation digest is invalid: {relative}")
        if _sha256(path) != digest:
            raise VerificationError(f"Native validation digest mismatch: {relative}")
    if recorded_paths != expected_paths:
        raise VerificationError("Native validation artifact inventory does not match native entrypoints")

    benchmark = _read_json(ROOT / "docs" / "benchmark-data.json")
    benchmark_summary = record.get("benchmark")
    if not isinstance(benchmark_summary, dict) or benchmark_summary != {
        "resolution": benchmark.get("resolution"),
        "frames_per_sample": benchmark.get("frames_per_sample"),
        "gpu": benchmark.get("gpu"),
    }:
        raise VerificationError("Native validation benchmark environment does not match benchmark data")


def _check_update_sources() -> None:
    config = _read_json(ROOT / "config" / "update_sources.json")
    sources = config.get("sources")
    if not isinstance(sources, list):
        raise VerificationError("config/update_sources.json must contain a sources list")
    sources_by_id = {
        source.get("id"): source
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("id"), str)
    }
    public_feed = _read_json(PUBLIC_FEED)
    public_source = sources_by_id.get(public_feed.get("feed_id"))
    if public_source is None:
        raise VerificationError("Public feed is not declared in config/update_sources.json")
    if (
        public_source.get("url") != PUBLIC_FEED_URL
        or public_source.get("enabled") is not True
        or public_source.get("trust") != "first_party"
    ):
        raise VerificationError("Public feed source must use the canonical HTTPS URL and be enabled")
    if public_source.get("auto_stage") is not False or public_source.get("auto_activate") is not False:
        raise VerificationError("Public feed must remain notification-only")

    local_feed = _read_json(LOCAL_FEED)
    local_source = sources_by_id.get(local_feed.get("feed_id"))
    if (
        local_source is None
        or local_source.get("url") != "registry/update-feed.local.json"
        or local_source.get("enabled") is not False
    ):
        raise VerificationError("Bundled local feed is not declared correctly")


def _check_embody_integration() -> None:
    """Validate the public, non-destructive live-QA integration contract."""

    installer_path = ROOT / "touchdesigner" / "scripts" / "install_dev_harness.py"
    validator_path = ROOT / "touchdesigner" / "scripts" / "validate_live_project.py"
    public_guide_path = ROOT / "docs" / "embody-envoy-integration.md"
    required = (
        EMBODY_INTEGRATION / "README.md",
        EMBODY_INTEGRATION / "project-context.json",
        EMBODY_INTEGRATION / "mcp-config.example.json",
        EMBODY_INTEGRATION / "envoy-validation-plan.json",
        installer_path,
        validator_path,
        public_guide_path,
    )
    missing = [path.relative_to(ROOT) for path in required if not path.is_file()]
    if missing:
        raise VerificationError(
            "Missing Embody integration files: " + ", ".join(map(str, missing))
        )

    context = _read_json(EMBODY_INTEGRATION / "project-context.json")
    catalog = (context.get("overview") or {}).get("catalog") or {}
    native = _read_json(ROOT / "docs" / "native-validation.json")
    native_build = (native.get("touchdesigner") or {}).get("build")
    if (
        context.get("schema_version") != 1
        or context.get("project_id") != "td-imagefx-library"
        or catalog.get("current_effect_ids") != EXPECTED_EFFECT_ID_COUNT
        or catalog.get("immutable_package_versions") != EXPECTED_PACKAGE_VERSION_COUNT
        or (context.get("overview") or {}).get("validated_touchdesigner_build")
        != native_build
    ):
        raise VerificationError(
            "Embody project context does not match the ImageFX catalog/native build"
        )
    network = context.get("network") or {}
    outputs = context.get("outputs") or {}
    if network.get("library") != "/project1/td_imagefx" or outputs.get(
        "primary_demo"
    ) != "/project1/imagefx_demo/out1_image":
        raise VerificationError("Embody project context has unexpected managed paths")

    example_path = EMBODY_INTEGRATION / "mcp-config.example.json"
    example_text = example_path.read_text(encoding="utf-8")
    example = _read_json(example_path)
    server = (example.get("mcpServers") or {}).get("td-knowledge") or {}
    arguments = server.get("args")
    if (
        server.get("type") != "stdio"
        or not isinstance(arguments, list)
        or "--project-context" not in arguments
        or "--faiss-db" not in arguments
        or "ABSOLUTE" not in example_text
        or "wenju" in example_text.lower()
    ):
        raise VerificationError(
            "Embody MCP example must remain portable and project-scoped"
        )

    plan = _read_json(EMBODY_INTEGRATION / "envoy-validation-plan.json")
    if (
        plan.get("schema_version") != 1
        or plan.get("project_id") != context["project_id"]
        or plan.get("mode") != "read-only"
    ):
        raise VerificationError("Envoy validation plan has an incompatible identity")
    tools = {
        call.get("tool")
        for stage in plan.get("stages", [])
        if isinstance(stage, dict)
        for call in stage.get("calls", [])
        if isinstance(call, dict)
    }
    required_tools = {
        "get_td_project_context",
        "query_td_knowledge",
        "get_td_info",
        "get_project_performance",
        "query_network",
        "exec_op_method",
        "get_op_errors",
        "execute_python",
        "capture_top",
    }
    if not required_tools.issubset(tools):
        raise VerificationError("Envoy validation plan is missing required audit tools")

    installer = installer_path.read_text(encoding="utf-8")
    if "project.save(" in installer or "_save_project_atomically" in installer:
        raise VerificationError("Development harness installer may not save a project")
    validator = validator_path.read_text(encoding="utf-8")
    for name, expected in (
        ("EXPECTED_PACKAGES", EXPECTED_EFFECT_ID_COUNT),
        ("EXPECTED_VERSIONS", EXPECTED_PACKAGE_VERSION_COUNT),
    ):
        match = re.search(rf"^{name}\s*=\s*(\d+)\s*$", validator, re.MULTILINE)
        if match is None or int(match.group(1)) != expected:
            raise VerificationError(
                f"Live validator {name} does not match the repository catalog"
            )


def _run(label: str, arguments: list[str], env: dict[str, str]) -> None:
    print(f"\n[verify] {label}", flush=True)
    subprocess.run(arguments, cwd=ROOT, env=env, check=True)


def main() -> int:
    if sys.version_info < (3, 11):
        print("[verify] Python 3.11 or newer is required", file=sys.stderr)
        return 1

    try:
        version = _check_versions()
        package_version_count, package_ids, latest_versions = _check_manifests()
        for feed_path in (PUBLIC_FEED, LOCAL_FEED):
            if not feed_path.is_file():
                raise VerificationError(f"Missing update feed: {feed_path.relative_to(ROOT)}")
        _check_update_sources()
        _check_embody_integration()
        _check_generated_artifacts(package_ids, latest_versions)
        _check_native_validation(version)
        _check_public_documentation()

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(ROOT / "src"), existing_pythonpath) if part
        )
        python = sys.executable
        _run(
            "Compile Python sources",
            [python, "-m", "compileall", "-q", "src", "tests", "tools", "touchdesigner"],
            env,
        )
        _run("Run unit tests", [python, "-m", "unittest", "discover", "-s", "tests", "-v"], env)
        _run(
            "Validate package manifests",
            [python, "-m", "tdimagefx", "validate", "packages", "--type", "package"],
            env,
        )
        for feed_path in (PUBLIC_FEED, LOCAL_FEED):
            _run(
                f"Validate {feed_path.relative_to(ROOT)}",
                [python, "-m", "tdimagefx", "validate", str(feed_path), "--type", "feed"],
                env,
            )
        _run(
            "Check generated effect gallery",
            [python, "tools/build_gallery.py", "--check"],
            env,
        )
        _run(
            "Check gallery visual baselines",
            [python, "tools/check_gallery.py"],
            env,
        )
        _run(
            "Check generated benchmark report",
            [python, "tools/benchmark_report.py", "--check"],
            env,
        )
    except (OSError, VerificationError, subprocess.CalledProcessError) as exc:
        print(f"\n[verify] FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        f"\n[verify] PASS: TD ImageFX {version}, {len(package_ids)} effect IDs / "
        f"{package_version_count} immutable versions, "
        "2 feeds, native artifacts, gallery and benchmarks",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
