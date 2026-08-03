import os
import urllib.request
from typing import List, Dict, Set

from core.apt_index import INDEX_ABSENT, debian_arch, fetch_index_text


def fetch_and_parse_packages_index(repo_url: str, suite: str, component: str = "main", arch: str = "amd64") -> Dict[str, str]:
    """
    Fetches the Packages index for a given repository, suite, component, and
    architecture, and returns a mapping of package_name -> deb_url.
    """
    base_repo_url = repo_url.rstrip("/")
    content_str = fetch_index_text(base_repo_url, suite, component, debian_arch(arch), timeout=15)

    if content_str is INDEX_ABSENT:
        print(f"[REPO FETCH] {base_repo_url} {suite}/{component} publishes no index for {debian_arch(arch)}.")
        return {}
    if not content_str:
        print(f"[REPO FETCH] Could not read the {suite}/{component} index from {base_repo_url}.")
        return {}

    package_deb_map = {}

    # Parse Debian control blocks
    blocks = content_str.split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        pkg_name = None
        rel_filename = None
        for line in block.splitlines():
            if line.startswith("Package:"):
                pkg_name = line.split(":", 1)[1].strip()
            elif line.startswith("Filename:"):
                rel_filename = line.split(":", 1)[1].strip()

        if pkg_name and rel_filename:
            # Full URL to deb package file
            full_deb_url = f"{base_repo_url}/{rel_filename}"
            # Store latest parsed version
            package_deb_map[pkg_name] = full_deb_url

    return package_deb_map


def download_edge_packages(recipe, workspace_path: str, exclude=frozenset()) -> List[str]:
    """
    Pre-downloads all Edge platform .deb packages for a recipe into
    workspace/mkosi.extra/opt/edge_packages/ so they can be installed via dpkg -i.
    Returns list of downloaded package file paths.

    exclude -- пакеты, которых нет под архитектуру рецепта; их уже вычеркнула
    предполётная проверка (core/arch_check.py).
    """
    dest_dir = os.path.join(workspace_path, "mkosi.extra", "opt", "edge_packages")
    if os.path.exists(dest_dir):
        import shutil
        shutil.rmtree(dest_dir, ignore_errors=True)
    os.makedirs(dest_dir, exist_ok=True)

    # Determine packages to fetch. The list (including the always-present core
    # Edge packages) comes from core.packages so the pre-flight architecture
    # check and the downloader can never disagree about what a recipe needs.
    from core.packages import resolve_package_list
    _, edge_pkgs = resolve_package_list(recipe, exclude=exclude)
    requested_pkgs: Set[str] = set(edge_pkgs)

    if not requested_pkgs:
        # Every Edge package was excluded (typically an arm64 recipe built
        # before the platform packages exist). Reading the indices would only
        # produce a handful of pointless requests and 404 warnings.
        print("[REPO DOWNLOADER] No Edge packages to fetch.")
        return []

    print(f"[REPO DOWNLOADER] Resolving Edge packages: {sorted(list(requested_pkgs))}...")

    repos = recipe.repositories if (recipe.repositories and isinstance(recipe.repositories, list)) else []
    if not repos:
        # Fallback default repos
        repos = [
            {"url": "https://edge.vitcompany.com/repo/bookworm/stable", "suite": "bookworm", "components": "main"},
            {"url": "https://edge.vitcompany.com/repo/bookworm/testing", "suite": "bookworm", "components": "main"}
        ]

    # Build master package map across all configured repos (later repos override earlier ones)
    master_map: Dict[str, str] = {}
    rel = recipe.release or "bookworm"

    for r in repos:
        if isinstance(r, dict) and r.get("url"):
            url = r.get("url")
            suite = r.get("suite") or rel
            comp = r.get("components") or "main"
            recipe_arch = getattr(recipe, "architecture", "amd64") or "amd64"
            repo_map = fetch_and_parse_packages_index(url, suite, comp, arch=recipe_arch)
            master_map.update(repo_map)

    downloaded_files = []

    for pkg_name in requested_pkgs:
        deb_url = master_map.get(pkg_name)
        if not deb_url:
            print(f"[REPO DOWNLOADER WARNING] Package '{pkg_name}' not found in package indices.")
            continue

        deb_filename = os.path.basename(deb_url)
        dest_file = os.path.join(dest_dir, deb_filename)

        # Persistent host cache directory for Edge deb packages
        global_cache_dir = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "cache", "deb_cache")
        os.makedirs(global_cache_dir, exist_ok=True)
        cached_deb = os.path.join(global_cache_dir, deb_filename)

        if os.path.exists(cached_deb) and os.path.getsize(cached_deb) > 0:
            print(f"[REPO DOWNLOADER CACHE HIT] Using cached {deb_filename} from {cached_deb}")
            import shutil
            shutil.copy2(cached_deb, dest_file)
            downloaded_files.append(dest_file)
            continue

        print(f"[REPO DOWNLOADER] Downloading {pkg_name} from {deb_url} -> {dest_file}...")
        try:
            req = urllib.request.Request(deb_url, headers={"User-Agent": "edge-duro-builder"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest_file, "wb") as out_f:
                out_f.write(resp.read())
            
            # Save copy to persistent host deb cache
            import shutil
            shutil.copy2(dest_file, cached_deb)

            downloaded_files.append(dest_file)
            print(f"[REPO DOWNLOADER SUCCESS] Downloaded {deb_filename} ({os.path.getsize(dest_file)} bytes)")
        except Exception as e:
            print(f"[REPO DOWNLOADER ERROR] Failed to download {pkg_name} from {deb_url}: {e}")

    return downloaded_files
