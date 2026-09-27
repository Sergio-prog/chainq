import os
import sys
import threading

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def enabled() -> bool:
    return sys.stderr.isatty() and os.environ.get("TERM") != "dumb"


def clear_line() -> None:
    if enabled():
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()


class Progress:
    def __init__(self, label: str, total: int | None = None):
        self.label = label
        self.total = total
        self.done = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def __enter__(self) -> "Progress":
        if enabled():
            self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()
            clear_line()

    def advance(self) -> None:
        self.done += 1

    def stage(self, label: str, total: int | None = None) -> None:
        self.label, self.total, self.done = label, total, 0

    def _spin(self) -> None:
        frame = 0
        while not self._stop.wait(0.08):
            count = f"  {self.done}/{self.total}" if self.total else ""
            sys.stderr.write(f"\r\033[K{FRAMES[frame % len(FRAMES)]} {self.label}{count}")
            sys.stderr.flush()
            frame += 1
