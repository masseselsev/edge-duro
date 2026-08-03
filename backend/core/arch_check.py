"""
Предполётная проверка доступности пакетов под архитектуру рецепта.

Пакеты дистрибутива уходят в Packages= mkosi, и apt валит весь билд минут через
десять после старта, если хоть одного из них нет под arm64. Проверка сверяет
список с именами из индексов binary-<arch> ещё до запуска mkosi, чтобы сборка
либо упала за пару секунд с внятным списком, либо (по галочке рецепта)
продолжилась без недоступных пакетов.

Смотрит только на имена верхнего уровня: если пакет под arm64 есть, а его
зависимость -- нет, apt всё равно упадёт. Такие случаи разбирает
core/apt_diagnostics.py уже по логу mkosi.
"""
import gzip
import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from core.apt_index import INDEX_ABSENT, debian_arch, fetch_index_text
from core.packages import is_critical, resolve_package_list

DEBIAN_MIRROR = "https://deb.debian.org/debian"
DEBIAN_COMPONENTS = ("main", "contrib", "non-free", "non-free-firmware")

UBUNTU_MIRROR = "http://archive.ubuntu.com/ubuntu"
UBUNTU_PORTS_MIRROR = "http://ports.ubuntu.com/ubuntu-ports"
UBUNTU_COMPONENTS = ("main", "restricted", "universe", "multiverse")

_CACHE_TTL_SECONDS = 24 * 60 * 60




@dataclass
class ArchCheckResult:
    checked: bool = False
    missing: List[Dict[str, str]] = field(default_factory=list)
    unreachable: List[str] = field(default_factory=list)
    # URL репозиториев рецепта, не публикующих ни одного индекса под эту
    # архитектуру. Такой источник незачем писать в sources.list.d образа --
    # на устройстве apt update ловил бы на нём 404 бесконечно.
    absent_repos: List[str] = field(default_factory=list)


def has_critical(result: "ArchCheckResult") -> bool:
    return any(m["reason"] == "critical" for m in result.missing)


def official_index_sources(distribution, release, architecture) -> List[Tuple[str, str, str]]:
    """
    Зеркала и компоненты ровно те, что берёт mkosi по умолчанию -- Mirror= в
    сгенерированном конфиге не задаётся. Ubuntu держит не-x86 архитектуры на
    отдельном хосте ports.ubuntu.com, на archive.ubuntu.com их индексов нет.
    """
    distro = (distribution or "debian").lower()
    suite = release or "bookworm"
    if "ubuntu" in distro:
        mirror = UBUNTU_PORTS_MIRROR if debian_arch(architecture) == "arm64" else UBUNTU_MIRROR
        return [(mirror, suite, comp) for comp in UBUNTU_COMPONENTS]
    return [(DEBIAN_MIRROR, suite, comp) for comp in DEBIAN_COMPONENTS]


def extract_package_names(text: str) -> Set[str]:
    """
    Из индекса нужны только имена. Полный парсер repo_browser здесь не годится:
    индекс Debian main -- порядка 65 тысяч станз, держать их словарями дорого.
    Имена из Provides: обязательны, иначе виртуальные пакеты вроде
    mail-transport-agent дадут ложное срабатывание.
    """
    names: Set[str] = set()
    for line in text.splitlines():
        if line.startswith("Package:"):
            name = line.split(":", 1)[1].strip()
            if name:
                names.add(name)
        elif line.startswith("Provides:"):
            for item in line.split(":", 1)[1].split(","):
                virtual = item.strip().split(" ")[0].strip()
                if virtual:
                    names.add(virtual)
    return names


def _cache_path(url: str, suite: str, component: str, arch: str) -> Optional[str]:
    ws_root = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
    cache_dir = os.path.join(ws_root, "cache", "apt_index")
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        return None
    key = hashlib.sha1(f"{url}|{suite}|{component}|{arch}".encode()).hexdigest()
    return os.path.join(cache_dir, f"{key}.txt.gz")


def _read_cache(path: Optional[str]) -> Optional[Set[str]]:
    if not path:
        return None
    try:
        if not os.path.exists(path):
            return None
        if time.time() - os.path.getmtime(path) > _CACHE_TTL_SECONDS:
            return None
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return {line.strip() for line in fh if line.strip()}
    except Exception:
        return None


def _write_cache(path: Optional[str], names: Set[str]) -> None:
    if not path:
        return
    try:
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(names)))
        os.replace(tmp, path)
    except Exception:
        pass


def _available_names(
    sources: List[Tuple[str, str, str]],
    arch: str,
    fetch: Callable[[str, str, str, str], Optional[str]],
    log: Callable[[str], None],
) -> Tuple[Set[str], List[Tuple[str, str, str]], List[Tuple[str, str, str]]]:
    """Возвращает (имена, недостижимые источники, отсутствующие источники)."""
    names: Set[str] = set()
    unreachable: List[Tuple[str, str, str]] = []
    absent: List[Tuple[str, str, str]] = []

    for source in sources:
        url, suite, component = source
        path = _cache_path(url, suite, component, arch)
        cached = _read_cache(path)
        if cached is not None:
            names |= cached
            continue

        text = fetch(url, suite, component, arch)
        if text is None:
            unreachable.append(source)
            continue
        if text is INDEX_ABSENT:
            # Намеренно не кешируется: 404 держится ровно до того дня, когда
            # репозиторий соберёт пакеты под эту архитектуру, а суточный кеш
            # заморозил бы устаревший ответ.
            absent.append(source)
            continue

        parsed = extract_package_names(text)
        _write_cache(path, parsed)
        names |= parsed
        log(f"[ARCH CHECK] Indexed {len(parsed)} package names from {url} {suite}/{component} [{arch}].")

    return names, unreachable, absent


def check_recipe_packages(recipe, log=print, fetch=None) -> ArchCheckResult:
    fetch = fetch or fetch_index_text
    arch = debian_arch(getattr(recipe, "architecture", "amd64"))

    official = list(official_index_sources(recipe.distribution, recipe.release, recipe.architecture))
    sources = list(official)
    for repo in (recipe.repositories or []):
        if isinstance(repo, dict) and repo.get("url"):
            suite = repo.get("suite") or recipe.release or "bookworm"
            for component in (repo.get("components") or "main").split():
                sources.append((repo["url"], suite, component))

    available, unreachable, absent = _available_names(sources, arch, fetch, log)

    def describe(source):
        url, suite, component = source
        return f"{url} {suite}/{component} [{arch}]"

    if unreachable:
        # Недоступный индекс означает "не знаю", а не "пакета нет". Молча
        # вырезать пакеты из образа из-за упавшего зеркала недопустимо, поэтому
        # проверка отменяется целиком.
        for source in unreachable:
            log(f"[ARCH CHECK WARNING] Package index unreachable: {describe(source)}")
        log("[ARCH CHECK] Architecture availability check skipped -- at least one package index could not be read.")
        return ArchCheckResult(checked=False, missing=[], unreachable=[describe(s) for s in unreachable])

    if absent and all(source in absent for source in official):
        # Официальное зеркало без единого индекса значит, что спрашивают не то
        # (например, опечатка в release), а не что дистрибутив опустел.
        # Объявлять отсутствующим весь список пакетов на таком основании нельзя.
        for source in absent:
            log(f"[ARCH CHECK WARNING] No package index published: {describe(source)}")
        log(f"[ARCH CHECK] Architecture availability check skipped -- the distribution mirror publishes no index for {recipe.release} [{arch}].")
        return ArchCheckResult(checked=False, missing=[], unreachable=[describe(s) for s in absent])

    for source in absent:
        log(f"[ARCH CHECK] {describe(source)} publishes no index -- its packages count as unavailable for {arch}.")

    # Репозиторий рецепта считается непригодным, только когда ни один его
    # компонент не публикует индекс: contrib может отсутствовать при живом main.
    official_urls = {url for url, _, _ in official}
    with_index = {source[0] for source in sources if source not in absent}
    absent_repos = [
        url for url in dict.fromkeys(source[0] for source in absent)
        if url not in official_urls and url not in with_index
    ]

    std_pkgs, edge_pkgs = resolve_package_list(recipe)
    missing: List[Dict[str, str]] = []

    for name in list(std_pkgs) + list(edge_pkgs):
        if name in available:
            continue
        missing.append({
            "name": name,
            "source": "edge" if name.lower().startswith("edge-") else "apt",
            "reason": "critical" if is_critical(name) else "not_in_index",
            "detail": "",
        })

    return ArchCheckResult(checked=True, missing=missing, unreachable=[],
                           absent_repos=absent_repos)
