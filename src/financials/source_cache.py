"""Short-lived annual source reuse owned by one refresh worker cohort."""
from __future__ import annotations

from pathlib import Path
import threading


class AnnualSourceCache:
    MAX_BYTES = 128 * 1024 * 1024

    def __init__(self, company_codes: tuple[int, ...]):
        self.company_codes = company_codes
        self.retained_bytes = 0
        self.active = True
        self._scope = None
        self._sources = {}
        self._frames = {}
        self._lock = threading.RLock()

    @staticmethod
    def signature(path):
        try:
            stat = Path(path).stat()
            return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
        except OSError:
            return None

    def configure(self, raw_dir, processed_dir, report_type, base_url) -> bool:
        scope = (Path(raw_dir).resolve(), Path(processed_dir).resolve(), report_type, base_url)
        if self._scope is not None and self._scope != scope:
            self.clear()
        self._scope = scope
        return self.active

    def clear(self) -> None:
        with self._lock:
            self._sources.clear()
            self._frames.clear()
            self.retained_bytes = 0
            self.active = False

    def _discard_source(self, zip_path) -> None:
        self._sources.pop(zip_path, None)
        for path, (source, frame, size) in list(self._frames.items()):
            if source == zip_path:
                self.retained_bytes -= size
                del self._frames[path]

    def prepared(self, zip_path) -> bool:
        zip_path = Path(zip_path).resolve()
        with self._lock:
            signatures = self._sources.get(zip_path)
            if self.active and signatures and all(
                self.signature(path) == signature for path, signature in signatures.items()
            ):
                return True
            self._discard_source(zip_path)
            return False

    def remember_prepared(self, zip_path, files, zip_signature) -> None:
        zip_path = Path(zip_path).resolve()
        with self._lock:
            self._discard_source(zip_path)
            signatures = {Path(path).resolve(): self.signature(path) for path in files}
            signatures[zip_path] = self.signature(zip_path)
            if (self.active and files and signatures[zip_path] == zip_signature
                    and all(signature is not None for signature in signatures.values())):
                self._sources[zip_path] = signatures

    def get(self, filepath):
        path = Path(filepath).resolve()
        with self._lock:
            entry = self._frames.get(path)
            if entry is not None and self.prepared(entry[0]):
                return entry[1].copy(deep=True)
        return None

    def retain(self, filepath, frame):
        path = Path(filepath).resolve()
        with self._lock:
            source = next((source for source, files in self._sources.items() if path in files), None)
            if source is not None and self.prepared(source):
                size = int(frame.memory_usage(index=True, deep=True).sum())
                if self.retained_bytes + size <= self.MAX_BYTES:
                    self._frames[path] = (source, frame, size)
                    self.retained_bytes += size
                    return frame.copy(deep=True)
        return frame
