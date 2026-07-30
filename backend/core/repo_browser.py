"""
Browsable APT repository index.

Parses a repository's Packages index into structured metadata for the recipe
package picker. Kept separate from repo_downloader, which only needs the
package -> .deb URL mapping used during builds.
"""
import gzip
import io
import lzma
import threading
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# (url, suite, component, arch) -> (fetched_at, [package dicts])
_CACHE: Dict[Tuple[str, str, str, str], Tuple[float, List[Dict[str, Any]]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 600

# A repository index is a few MB of text; a package list far larger than this
# indicates something unexpected, so cap what we hold in memory per repo.
_MAX_PACKAGES = 200_000


def _http_get(url: str, timeout: int = 20) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "edge-duro-builder"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _fetch_index_text(repo_url: str, suite: str, component: str, arch: str) -> Optional[str]:
    """
    Fetches the Packages index, trying the compressions Debian archives publish
    in descending order of ubiquity. Returns None when the repo is unreachable
    or has no index for this suite/component/arch.
    """
    base = repo_url.rstrip("/")
    stem = f"{base}/dists/{suite}/{component}/binary-{arch}/Packages"

    for suffix, decoder in (
        (".gz", lambda b: gzip.GzipFile(fileobj=io.BytesIO(b)).read()),
        (".xz", lzma.decompress),
        ("", lambda b: b),
    ):
        raw = _http_get(stem + suffix)
        if raw is None:
            continue
        try:
            return decoder(raw).decode("utf-8", errors="replace")
        except Exception:
            continue
    return None


def _parse_index(text: str) -> List[Dict[str, Any]]:
    """
    Parses RFC822-style stanzas into package dicts, keeping only the highest
    version seen for each package name (a repo may carry several).
    """
    by_name: Dict[str, Dict[str, Any]] = {}

    for stanza in text.split("\n\n"):
        if not stanza.strip():
            continue

        fields: Dict[str, str] = {}
        # In a Packages stanza the Description field's first line is the short
        # summary and the indented continuation lines are the extended body, so
        # the summary is captured before continuations are folded in.
        summary = ""
        key = None
        for line in stanza.splitlines():
            if not line:
                continue
            if line[0] in " \t":
                # Continuation of the previous field (long descriptions).
                if key:
                    fields[key] += " " + line.strip()
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            fields[key] = value.strip()
            if key == "Description":
                summary = value.strip()

        name = fields.get("Package")
        if not name:
            continue

        description = fields.get("Description", "")

        try:
            size = int(fields.get("Installed-Size", "0") or 0)
        except ValueError:
            size = 0

        entry = {
            "name": name,
            "version": fields.get("Version", ""),
            "section": fields.get("Section", "") or "misc",
            "architecture": fields.get("Architecture", ""),
            "summary": summary,
            "description": description.strip(),
            "depends": fields.get("Depends", ""),
            "installed_size_kb": size,
        }

        prev = by_name.get(name)
        if prev is None or _version_gt(entry["version"], prev["version"]):
            by_name[name] = entry

        if len(by_name) >= _MAX_PACKAGES:
            break

    return sorted(by_name.values(), key=lambda p: p["name"])


def _version_key(version: str) -> List[Any]:
    """
    Crude but adequate ordering for picking the newest stanza of a package.
    Not a full dpkg version comparison; it only has to break ties within one
    repository index, where entries are already near-identical.
    """
    import re
    parts: List[Any] = []
    for chunk in re.split(r'[.\-+~:]', version or ""):
        if chunk.isdigit():
            parts.append((1, int(chunk)))
        elif chunk:
            parts.append((0, chunk))
    return parts


def _version_gt(a: str, b: str) -> bool:
    try:
        return _version_key(a) > _version_key(b)
    except Exception:
        return (a or "") > (b or "")


def get_packages(
    repo_url: str,
    suite: str,
    component: str = "main",
    arch: str = "amd64",
    force_refresh: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """
    Returns the parsed package list for a repository component, cached for
    _CACHE_TTL_SECONDS so typing in the picker does not re-download the index.
    Returns None when the index could not be fetched, which the caller must
    distinguish from an empty-but-reachable repository.
    """
    key = (repo_url.rstrip("/"), suite, component, arch)

    if not force_refresh:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and (time.time() - hit[0]) < _CACHE_TTL_SECONDS:
                return hit[1]

    text = _fetch_index_text(repo_url, suite, component, arch)
    if text is None:
        return None

    packages = _parse_index(text)
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), packages)
    return packages


def search(
    packages: List[Dict[str, Any]],
    query: str = "",
    section: str = "",
    limit: int = 200,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Filters server-side and returns (page, total_matches). Matching is done
    here rather than in the browser because a full Debian component carries
    tens of thousands of packages.
    """
    q = (query or "").strip().lower()
    sec = (section or "").strip().lower()

    matched = []
    for p in packages:
        if sec and p.get("section", "").lower() != sec:
            continue
        if q and q not in p["name"].lower() and q not in p.get("summary", "").lower():
            continue
        matched.append(p)

    # Exact name matches first, then prefix matches, then the rest.
    if q:
        def rank(p: Dict[str, Any]) -> Tuple[int, str]:
            name = p["name"].lower()
            if name == q:
                return (0, name)
            if name.startswith(q):
                return (1, name)
            return (2, name)

        matched.sort(key=rank)

    total = len(matched)
    return matched[offset:offset + limit], total


def sections(packages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for p in packages:
        s = p.get("section", "") or "misc"
        counts[s] = counts.get(s, 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(counts.items())]
