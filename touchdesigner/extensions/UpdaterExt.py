"""Safe, notify-only update checker for TouchDesigner.

Network work happens on a Python worker thread. The worker only writes JSON to disk;
all operator access remains on TouchDesigner's main thread.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


MAX_FEED_BYTES = 2 * 1024 * 1024
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original_scheme = urllib.parse.urlparse(req.full_url).scheme.lower()
        redirected_scheme = urllib.parse.urlparse(newurl).scheme.lower()
        if original_scheme == "https" and redirected_scheme != "https":
            raise ValueError("HTTPS update feeds may only redirect to HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UpdaterExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self._thread = None
        self._scheduled = False
        self._schedule_generation = 0

    def _root(self) -> Path:
        root_par = self.ownerComp.par["Rootfolder"]
        value = str(root_par.eval()).strip() if root_par is not None else ""
        return Path(value or project.folder).resolve()

    @staticmethod
    def _version_key(version):
        match = _SEMVER_RE.fullmatch(str(version))
        if match is None:
            raise ValueError("Invalid semantic version: {!r}".format(version))
        core = (int(match.group("major")), int(match.group("minor")), int(match.group("patch")))
        prerelease = match.group("pre")
        if prerelease is None:
            return core + (1, ())
        identifiers = tuple(
            (0, int(identifier)) if identifier.isdigit() else (1, identifier)
            for identifier in prerelease.split(".")
        )
        return core + (0, identifiers)

    @staticmethod
    def _load_json_url(url, timeout):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("https", "file"):
            raise ValueError("Only HTTPS and file update feeds are allowed")
        request = urllib.request.Request(url, headers={"User-Agent": "TD-ImageFX-Updater/0.1"})
        opener = urllib.request.build_opener(_HttpsOnlyRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            final_scheme = urllib.parse.urlparse(response.geturl()).scheme.lower()
            if final_scheme != parsed.scheme.lower():
                raise ValueError("Update feed changed URL scheme")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_FEED_BYTES:
                raise ValueError("Update feed exceeds the 2 MiB size limit")
            payload = response.read(MAX_FEED_BYTES + 1)
            if len(payload) > MAX_FEED_BYTES:
                raise ValueError("Update feed exceeds the 2 MiB size limit")
            return json.loads(payload.decode("utf-8"))

    @classmethod
    def _worker_check(cls, root, channel, timeout, output_path):
        result = {
            "schema_version": 1,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "complete",
            "updates": [],
            "errors": [],
            "sources_checked": 0,
        }
        try:
            source_path = root / "config" / "update_sources.json"
            config = json.loads(source_path.read_text(encoding="utf-8")) if source_path.is_file() else {"sources": []}
            installed = {}
            for manifest_path in (root / "packages").glob("*/**/package.json"):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                package_id = manifest.get("id")
                version = manifest.get("version")
                if package_id and version and (package_id not in installed or cls._version_key(version) > cls._version_key(installed[package_id])):
                    installed[package_id] = version

            for source in config.get("sources", []):
                if not source.get("enabled", False):
                    continue
                result["sources_checked"] += 1
                try:
                    feed_url = str(source["url"])
                    if not urllib.parse.urlparse(feed_url).scheme:
                        feed_url = (root / feed_url).resolve().as_uri()
                    feed = cls._load_json_url(feed_url, timeout)
                    for package in feed.get("packages", []):
                        package_id = package.get("id")
                        current = installed.get(package_id)
                        releases = [release for release in package.get("releases", []) if release.get("channel") == channel and not release.get("yanked", False)]
                        if not releases:
                            continue
                        latest = max(releases, key=lambda release: cls._version_key(release["version"]))
                        if current is None or cls._version_key(latest["version"]) > cls._version_key(current):
                            result["updates"].append({
                                "id": package_id,
                                "name": package.get("name", package_id),
                                "installed": current,
                                "available": latest["version"],
                                "channel": latest.get("channel"),
                                "requires_restart": bool(latest.get("requires_restart", False)),
                                "permissions_changed": bool(latest.get("permissions_changed", False)),
                                "changelog": latest.get("changelog", ""),
                                "source": source.get("id", source.get("url")),
                            })
                except Exception as exc:
                    result["errors"].append({"source": source.get("id", source.get("url", "unknown")), "error": str(exc)})
        except Exception as exc:
            result["status"] = "failed"
            result["errors"].append({"source": "local", "error": str(exc)})

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output_path)

    def CheckUpdates(self):
        if self._thread is not None and self._thread.is_alive():
            return False
        root = self._root()
        output = root / ".imagefx" / "update-status.json"
        self.ownerComp.par.Status = "Checking for updates..."
        self.ownerComp.par.Lastcheck = ""
        self._thread = threading.Thread(
            target=self._worker_check,
            args=(root, self.ownerComp.par.Channel.eval(), float(self.ownerComp.par.Timeout), output),
            daemon=True,
            name="TDImageFXUpdateCheck",
        )
        self._thread.start()
        run("op({!r}).Poll()".format(self.ownerComp.path), delayMilliSeconds=250, wallTime=True, delayRef=op.TDResources)
        return True

    def Poll(self):
        if self._thread is not None and self._thread.is_alive():
            run("op({!r}).Poll()".format(self.ownerComp.path), delayMilliSeconds=250, wallTime=True, delayRef=op.TDResources)
            return False
        status_path = self._root() / ".imagefx" / "update-status.json"
        try:
            result = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.ownerComp.par.Status = "Update check failed: {}".format(exc)
            return False
        table = self.ownerComp.op("update_results")
        table.setSize(0, 0)
        table.appendRow(("id", "installed", "available", "channel", "restart", "permissions_changed", "source", "changelog"))
        for item in result.get("updates", []):
            table.appendRow((
                item.get("id", ""), item.get("installed") or "not installed", item.get("available", ""),
                item.get("channel", ""), str(item.get("requires_restart", False)),
                str(item.get("permissions_changed", False)), item.get("source", ""), item.get("changelog", ""),
            ))
        self.ownerComp.par.Lastcheck = result.get("checked_at", "")
        if result.get("errors"):
            self.ownerComp.par.Status = "{} update(s), {} source error(s)".format(len(result.get("updates", [])), len(result["errors"]))
        elif result.get("sources_checked", 0) == 0:
            self.ownerComp.par.Status = "No enabled update sources"
        else:
            self.ownerComp.par.Status = "{} update(s) available".format(len(result.get("updates", [])))
        return True

    def StartAutoCheck(self):
        if not bool(self.ownerComp.par.Autocheck):
            return False
        if not self._scheduled:
            self._scheduled = True
            self._schedule_generation += 1
            generation = self._schedule_generation
            run(
                "op({!r}).AutoTick({})".format(self.ownerComp.path, generation),
                delayMilliSeconds=1500,
                wallTime=True,
                delayRef=op.TDResources,
            )
        return True

    def StopAutoCheck(self):
        self._schedule_generation += 1
        self._scheduled = False
        return True

    def AutoTick(self, generation=None):
        """Run one promoted auto-check tick and schedule the next one."""
        if generation is not None and generation != self._schedule_generation:
            return False
        self._scheduled = False
        if not bool(self.ownerComp.par.Autocheck):
            return False
        self.CheckUpdates()
        hours = max(float(self.ownerComp.par.Intervalhours), 1.0 / 60.0)
        self._scheduled = True
        run(
            "op({!r}).AutoTick({})".format(self.ownerComp.path, self._schedule_generation),
            delayMilliSeconds=int(hours * 3600000),
            wallTime=True,
            delayRef=op.TDResources,
        )
        return True
