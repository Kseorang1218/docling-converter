import hashlib
import json
import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .errors import ConversionError

_log = logging.getLogger(__name__)

MANIFEST_FILENAME = ".doclings.json"


@dataclass(frozen=True)
class SourceIdentity:
    name: str
    sha256: str
    path: Path | None = None

    @classmethod
    def from_path(cls, path: Path) -> "SourceIdentity":
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return cls(name=path.name, sha256=digest.hexdigest(), path=path.resolve())


@contextmanager
def staging_directory(output_root: Path) -> Iterator[Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".doclings-stage-", dir=output_root))
    try:
        yield stage
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _manifest_hash(directory: Path) -> str | None:
    manifest_path = directory / MANIFEST_FILENAME
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    value = data.get("source", {}).get("sha256")
    return value if isinstance(value, str) else None


def choose_output_directory(
    output_root: Path,
    title: str,
    identity: SourceIdentity,
    *,
    overwrite: bool = False,
) -> Path:
    preferred = output_root / title
    if (
        overwrite
        or not preferred.exists()
        or _manifest_hash(preferred) == identity.sha256
    ):
        return preferred

    hashed = output_root / f"{title}--{identity.sha256[:8]}"
    if not hashed.exists() or _manifest_hash(hashed) == identity.sha256:
        return hashed

    counter = 2
    while True:
        candidate = output_root / f"{title}--{identity.sha256[:8]}-{counter}"
        if not candidate.exists() or _manifest_hash(candidate) == identity.sha256:
            return candidate
        counter += 1


def _write_manifest(
    stage: Path,
    identity: SourceIdentity,
    backend: str,
    markdown_filename: str,
) -> None:
    data = {
        "schema_version": 1,
        "source": {"name": identity.name, "sha256": identity.sha256},
        "backend": backend,
        "markdown": markdown_filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (stage / MANIFEST_FILENAME).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _remove_backup(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def publish_directory(
    stage: Path,
    output_root: Path,
    title: str,
    identity: SourceIdentity,
    backend: str,
    *,
    overwrite: bool = False,
) -> Path:
    target = choose_output_directory(
        output_root, title, identity, overwrite=overwrite
    )
    markdown_path = stage / f"{title}.md"
    if not markdown_path.is_file():
        raise ConversionError(
            f"Expected markdown file was not produced: {markdown_path.name}"
        )
    if (
        identity.path is not None
        and target.resolve() in identity.path.resolve().parents
    ):
        raise ConversionError(
            f"Refusing to replace an output directory that contains the input PDF: {target}"
        )
    _write_manifest(stage, identity, backend, f"{title}.md")

    if not target.exists():
        os.replace(stage, target)
        return target

    backup = output_root / f".{target.name}.backup-{os.getpid()}"
    suffix = 2
    while backup.exists():
        backup = output_root / f".{target.name}.backup-{os.getpid()}-{suffix}"
        suffix += 1

    os.replace(target, backup)
    try:
        os.replace(stage, target)
    except Exception:
        try:
            os.replace(backup, target)
        except OSError as restore_error:
            raise OSError(
                f"Result publish and rollback both failed; backup remains at {backup}"
            ) from restore_error
        raise

    try:
        _remove_backup(backup)
    except OSError as exc:
        _log.warning("이전 결과 백업을 삭제하지 못했습니다: %s (%s)", backup, exc)
    return target
