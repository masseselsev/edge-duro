"""
Разбор жалоб apt/dpkg из лога mkosi.

Предполётная проверка (core/arch_check.py) видит только имена верхнего уровня.
Если пакет под нужную архитектуру есть, а его зависимость -- нет, apt всё равно
уронит билд, и без разбора лога пользователь увидит только "mkosi exited with
return code 1". Здесь из потока лога вылавливаются строки, по которым понятно,
какого пакета не хватило.
"""
import re
from typing import Dict, List

_UNABLE_TO_LOCATE = re.compile(r"Unable to locate package (\S+)")
_NO_CANDIDATE = re.compile(r"Package '([^']+)' has no installation candidate")
_UNMET = re.compile(r"^\s*(\S+)\s*:\s*(?:Pre-)?Depends:\s*(\S+).*but it is not installable")

_MARKER_LINES = (
    "The following packages have unmet dependencies",
    "Unsatisfied dependencies",
    "Depends:",
    "Unable to locate package",
    "has no installation candidate",
)


def is_diagnostic_line(line: str) -> bool:
    return any(marker in line for marker in _MARKER_LINES)


def _entry(name: str, detail: str) -> Dict[str, str]:
    return {
        "name": name,
        "source": "edge" if name.lower().startswith("edge-") else "apt",
        "reason": "dependency",
        "detail": detail.strip(),
    }


def parse_diagnostics(lines: List[str]) -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    seen = set()

    for line in lines:
        name = None
        unmet = _UNMET.search(line)
        if unmet:
            # Виноват не пакет слева, а недоступная зависимость справа.
            name = unmet.group(2)
        else:
            for pattern in (_UNABLE_TO_LOCATE, _NO_CANDIDATE):
                match = pattern.search(line)
                if match:
                    name = match.group(1)
                    break

        if not name or name in seen:
            continue
        seen.add(name)
        found.append(_entry(name, line))

    return found
