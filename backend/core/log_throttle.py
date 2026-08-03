"""
Схлопывание подряд идущих одинаковых строк лога сборки.

Зависший apt способен выдавать одну и ту же строку тысячи раз: реальный случай
-- 39 888 копий "Tried to start delayed item ... but failed" за 33 минуты,
7.4 МБ в builds.log_output и рост без предела. Каждая строка едет в Postgres и
в SSE-поток, поэтому повторы отсекаются до записи.

Существующий троттлинг процентов в build_image.py не помогает: он смотрит
только на строки вида "NN%".
"""
from typing import List, Optional


class RepeatCollapser:
    """
    feed(line) возвращает список строк, которые следует записать: саму строку,
    если она новая, пустой список, если это повтор, и сводку о законченном
    повторе перед новой строкой. flush() закрывает незавершённый повтор.
    """

    def __init__(self, heartbeat: int = 500):
        # Совсем немой лог не даёт отличить зависание от медленной работы,
        # поэтому длинный повтор всё же отмечается раз в heartbeat строк.
        self._heartbeat = heartbeat
        self._last: Optional[str] = None
        self._repeats = 0

    @staticmethod
    def _summary(count: int) -> str:
        times = "time" if count == 1 else "times"
        return f"[repeated {count} more {times}]"

    def feed(self, line: str) -> List[str]:
        if line == self._last:
            self._repeats += 1
            if self._heartbeat and self._repeats % self._heartbeat == 0:
                return [f"[still repeating, {self._repeats} times]"]
            return []

        out = self.flush()
        self._last = line
        self._repeats = 0
        out.append(line)
        return out

    def flush(self) -> List[str]:
        if self._repeats:
            out = [self._summary(self._repeats)]
            self._repeats = 0
            return out
        return []
