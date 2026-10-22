"""Media limits shared by browser uploads and local MCP jobs."""

from pathlib import Path


ALLOWED_EXTENSIONS = {
    ".mp3", ".mp4", ".m4a", ".m4v", ".wav", ".flac", ".ogg", ".oga",
    ".opus", ".webm", ".mov", ".mkv", ".avi", ".aac", ".aiff",
    ".wma", ".mpeg", ".mpga",
}
MAX_FILES = 20
MAX_FILE_BYTES = 1_000_000_000
FORMATS = {"txt", "srt", "vtt", "json"}


def validate_local_file(value: str) -> tuple[Path, int]:
    """Resolve an existing media file without taking ownership of it."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Use um caminho absoluto para o arquivo local")
    try:
        path = path.resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Não é um arquivo: {path}")
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"Não foi possível ler o arquivo: {value}: {exc}") from exc
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Formato não aceito: {path.name}")
    if size == 0:
        raise ValueError(f"Arquivo vazio: {path.name}")
    if size > MAX_FILE_BYTES:
        raise ValueError(f"Arquivo maior que 1 GB: {path.name}")
    return path, size
