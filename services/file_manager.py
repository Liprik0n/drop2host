import os
import shutil
import uuid
import zipfile
from pathlib import Path

from config import SITES_DIR


def get_project_dir(username: str, slug: str) -> Path:
    return SITES_DIR / username / slug


def generate_random_slug() -> str:
    return uuid.uuid4().hex[:8]


def save_html_file(username: str, slug: str, content: bytes, filename: str = "index.html"):
    """Save a single HTML file into the project directory."""
    project_dir = get_project_dir(username, slug)
    project_dir.mkdir(parents=True, exist_ok=True)
    target = project_dir / "index.html"
    target.write_bytes(content)


def save_zip_archive(username: str, slug: str, zip_data: bytes):
    """Extract a ZIP archive into the project directory."""
    project_dir = get_project_dir(username, slug)
    # Clear existing files if overwriting
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(zip_data)
        tmp_path = tmp.name

    try:
        with zipfile.ZipFile(tmp_path, "r") as zf:
            # Security: check for path traversal
            for member in zf.namelist():
                member_path = Path(member)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError(f"Опасный путь в архиве: {member}")

            zf.extractall(project_dir)

        # If archive contains a single top-level directory, move its contents up
        _flatten_single_dir(project_dir)
        # If no index.html but there's a single .html file, rename it
        _ensure_index_html(project_dir)
    finally:
        os.unlink(tmp_path)


def _flatten_single_dir(project_dir: Path):
    """If extracted contents are a single directory, move files up one level."""
    entries = list(project_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner_dir = entries[0]
        for item in inner_dir.iterdir():
            shutil.move(str(item), str(project_dir / item.name))
        inner_dir.rmdir()


def _ensure_index_html(project_dir: Path):
    """If no index.html exists but there's a single .html file, rename it to index.html."""
    index = project_dir / "index.html"
    if index.exists():
        return
    html_files = list(project_dir.glob("*.html")) + list(project_dir.glob("*.htm"))
    if len(html_files) == 1:
        html_files[0].rename(index)


def delete_project_files(username: str, slug: str):
    """Remove the project directory from disk."""
    project_dir = get_project_dir(username, slug)
    if project_dir.exists():
        shutil.rmtree(project_dir)

    # Clean up empty user directory
    user_dir = SITES_DIR / username
    if user_dir.exists() and not any(user_dir.iterdir()):
        user_dir.rmdir()


def project_exists_on_disk(username: str, slug: str) -> bool:
    return get_project_dir(username, slug).exists()
