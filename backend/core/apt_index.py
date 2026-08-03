"""
Выкачка индексов Packages из APT-репозиториев.

Единственное место, где живёт эта операция. Раньше её вариант был в
repo_browser (просмотр пакетов в UI), в repo_downloader (предзагрузка
edge-пакетов) и в arch_check (проверка архитектуры). Копии расходились:
предзагрузчик, например, тянул binary-amd64 независимо от архитектуры рецепта,
потому что правку внесли только в одну из них.

Разбор индекса намеренно остаётся у вызывающих: одному нужен набор имён,
другому отображение имя -> URL, третьему полные метаданные для UI.
"""
import gzip
import io
import lzma
import urllib.error
import urllib.request
from typing import Optional, Tuple

USER_AGENT = "edge-duro-builder"


class _IndexAbsent:
    """
    Индекс не существует, и это достоверно: сервер ответил 404 на все варианты
    сжатия. Отличается от None ("не знаю"): 404 на binary-arm64 значит, что под
    эту архитектуру репозиторий ничего не собирает, а None -- что до зеркала не
    дозвонились и выводов делать нельзя.
    """

    def __repr__(self):
        return "INDEX_ABSENT"


INDEX_ABSENT = _IndexAbsent()


def debian_arch(architecture) -> str:
    """Приводит имя архитектуры к тому, что стоит в путях binary-<arch>."""
    arch = (architecture or "amd64").lower()
    return "arm64" if arch in ("arm64", "aarch64") else "amd64"


def http_get(url: str, timeout: int = 30) -> Tuple[Optional[int], Optional[bytes]]:
    """
    Возвращает (http_status, body). status равен None, когда HTTP-ответа не было
    вовсе -- DNS, TCP, TLS, таймаут.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


def index_url(repo_url: str, suite: str, component: str, arch: str) -> str:
    return f"{repo_url.rstrip('/')}/dists/{suite}/{component}/binary-{arch}/Packages"


def fetch_index_text(repo_url: str, suite: str, component: str = "main",
                     arch: str = "amd64", timeout: int = 30):
    """
    Тянет Packages в тех сжатиях, что публикуют архивы Debian и Ubuntu.

    Возвращает текст индекса, INDEX_ABSENT (все варианты ответили 404) либо
    None (хоть один вариант не ответил или отдал нечитаемое -- достоверного
    вывода сделать нельзя).
    """
    stem = index_url(repo_url, suite, component, arch)
    only_missing = True

    for suffix, decoder in (
        (".gz", lambda b: gzip.GzipFile(fileobj=io.BytesIO(b)).read()),
        (".xz", lzma.decompress),
        ("", lambda b: b),
    ):
        status, raw = http_get(stem + suffix, timeout=timeout)
        if raw is None:
            if status != 404:
                only_missing = False
            continue
        try:
            return decoder(raw).decode("utf-8", errors="replace")
        except Exception:
            # Ответ есть, но распаковать не вышло -- сервер ведёт себя
            # неожиданно, "индекса нет" отсюда не следует.
            only_missing = False
            continue

    return INDEX_ABSENT if only_missing else None


def publishes_index(repo_url: str, suite: str, component: str, arch: str,
                    timeout: int = 15) -> bool:
    """
    Публикует ли репозиторий индекс под эту архитектуру. Недостижимое зеркало
    считается публикующим: молча выбросить источник из-за сбоя сети хуже, чем
    оставить лишний.
    """
    return fetch_index_text(repo_url, suite, component, arch, timeout=timeout) is not INDEX_ABSENT
