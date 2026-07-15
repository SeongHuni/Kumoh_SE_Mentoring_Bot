from __future__ import annotations

from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile


class RollbackFailure(RuntimeError):
    def __init__(
        self,
        failed_target_names: tuple[str, ...],
        failed_backup_paths: tuple[Path, ...],
        cause: OSError,
    ) -> None:
        self.failed_target_names = failed_target_names
        self.failed_backup_paths = failed_backup_paths
        target_names = ", ".join(failed_target_names)
        backup_paths = ", ".join(str(path) for path in failed_backup_paths)
        message = f"{target_names} 복구 실패"
        if backup_paths:
            message += f"; 보존된 백업: {backup_paths}"
        super().__init__(message)
        self.__cause__ = cause


def _cleanup_artifacts(
    paths: list[Path | None],
    preserve: set[Path] | None = None,
) -> OSError | None:
    first_error: OSError | None = None
    preserve = preserve or set()
    for path in paths:
        if path is None or path in preserve:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            first_error = first_error or exc
    return first_error


def _stage_text(target: Path, content: str, *, label: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=str(target.parent),
            suffix=".tmp",
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
    except OSError as exc:
        cleanup_error = _cleanup_artifacts([temporary_path])
        if cleanup_error is not None:
            raise RuntimeError(
                f"{label} 임시 파일 정리에 실패했습니다: {cleanup_error}"
            ) from exc
        raise
    if temporary_path is None:
        raise RuntimeError(f"{label} 임시 파일을 만들지 못했습니다.")
    return temporary_path


def _backup_target(target: Path, *, label: str) -> Path | None:
    if not target.exists():
        return None
    with NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=str(target.parent),
        suffix=".bak",
    ) as handle:
        backup_path = Path(handle.name)
    try:
        copyfile(target, backup_path)
    except OSError as exc:
        cleanup_error = _cleanup_artifacts([backup_path])
        if cleanup_error is not None:
            raise RuntimeError(
                f"{label} 백업 파일 정리에 실패했습니다: {cleanup_error}"
            ) from exc
        raise
    return backup_path


def _rollback_reports(
    targets: tuple[Path, ...],
    backups: tuple[Path | None, ...],
) -> None:
    first_error: OSError | None = None
    failed_targets: list[str] = []
    failed_backup_paths: list[Path] = []
    for target, backup in zip(targets, backups, strict=True):
        try:
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                backup.replace(target)
        except OSError as exc:
            failed_targets.append(target.name)
            if backup is not None:
                failed_backup_paths.append(backup)
            first_error = first_error or exc
    if first_error is not None:
        raise RollbackFailure(
            tuple(failed_targets),
            tuple(failed_backup_paths),
            first_error,
        ) from first_error


def write_text_reports(
    reports: tuple[tuple[Path, str], ...],
    *,
    label: str,
) -> None:
    if not reports:
        raise ValueError(f"{label} 출력이 비어 있습니다.")
    targets = tuple(target for target, _content in reports)
    staged: list[Path] = []
    backups: list[Path | None] = []
    commit_started = False
    try:
        staged.extend(
            _stage_text(target, content, label=label) for target, content in reports
        )
        backups.extend(_backup_target(target, label=label) for target in targets)
        commit_started = True
        for target, temporary_path in zip(targets, staged, strict=True):
            temporary_path.replace(target)
    except Exception as original_error:
        rollback_error: Exception | None = None
        preserved_backups: set[Path] = set()
        if commit_started:
            try:
                _rollback_reports(targets, tuple(backups))
            except RollbackFailure as exc:
                rollback_error = exc
                preserved_backups = set(exc.failed_backup_paths)
            except Exception as exc:
                rollback_error = exc
        cleanup_error = _cleanup_artifacts(
            [*staged, *backups],
            preserve=preserved_backups,
        )
        if rollback_error is not None:
            message = f"{label} 롤백에 실패했습니다: {rollback_error}"
            if cleanup_error is not None:
                message += f"; 임시 파일 정리 실패: {cleanup_error}"
            raise RuntimeError(message) from original_error
        if cleanup_error is not None:
            raise RuntimeError(
                f"{label} 임시 파일 정리에 실패했습니다: {cleanup_error}"
            ) from original_error
        raise

    cleanup_error = _cleanup_artifacts([*staged, *backups])
    if cleanup_error is not None:
        raise RuntimeError(
            f"{label} 임시 파일 정리에 실패했습니다: {cleanup_error}"
        ) from cleanup_error
