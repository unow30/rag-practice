import hashlib
import logging
import os

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

_observer: Observer | None = None


class _DocumentFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            _mark_file_changed(event.src_path)

    def on_created(self, event):
        # 파일 교체(복사/덮어쓰기) 시 on_created가 발생하는 경우 처리
        if not event.is_directory and event.src_path.lower().endswith(".pdf"):
            _mark_file_changed(event.src_path)

    def on_moved(self, event):
        # 파일명 변경 시 처리
        if not event.is_directory and event.dest_path.lower().endswith(".pdf"):
            _mark_file_changed(event.dest_path)


def _compute_sha256(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _mark_file_changed(file_path: str) -> None:
    from backend.models.database import SessionLocal
    from backend.models.document import Document, DocumentStatus

    basename = os.path.basename(file_path)
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(
            Document.file_path.endswith(basename)
        ).first()
        if not doc or doc.status != DocumentStatus.READY or doc.file_changed:
            return

        new_hash = _compute_sha256(file_path)
        if new_hash != doc.file_hash:
            doc.file_changed = True
            db.commit()
            logger.info("content changed: %s", doc.name)
        else:
            logger.debug("mtime updated but content unchanged: %s", doc.name)
    except Exception:
        logger.exception("error marking file changed: %s", file_path)
    finally:
        db.close()


def start_file_watcher(watch_dir: str) -> None:
    global _observer
    os.makedirs(watch_dir, exist_ok=True)
    _observer = Observer()
    _observer.schedule(_DocumentFileHandler(), watch_dir, recursive=False)
    _observer.start()
    logger.info("file watcher started: %s", watch_dir)


def stop_file_watcher() -> None:
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None
