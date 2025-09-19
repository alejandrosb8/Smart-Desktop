import pathlib
import json
import logging
import shutil
import os
from pathlib import Path
from google import genai
from google.genai import types as genai_types
import PyPDF2
import docx
import mimetypes
import keyring
import datetime
import fnmatch
from typing import Callable

MOVEMENT_LOG_FILE = "movement_log.json"

# Keyring constants
KEYRING_SERVICE = "intelligent-desktop"
KEYRING_USERNAME = "gemini"

def setup_logging(log_callback):
    """Configure a logger that writes to a file and forwards to a callback (GUI)."""
    logger = logging.getLogger("organizer")
    logger.setLevel(logging.INFO)
    
    # Evitar añadir manejadores duplicados
    if not logger.handlers:
        # Manejador para el archivo
        file_handler = logging.FileHandler("organizer.log", encoding="utf-8")
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Manejador para la GUI
        class CallbackHandler(logging.Handler):
            def emit(self, record):
                log_callback(self.format(record))
        
        callback_handler = CallbackHandler()
        callback_formatter = logging.Formatter('%(message)s')
        callback_handler.setFormatter(callback_formatter)
        logger.addHandler(callback_handler)

    return logger

def set_api_key(api_key: str):
    """Store the API key securely in the system keyring."""
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)

def get_api_key() -> str | None:
    """Retrieve the API key from the system keyring."""
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None

def delete_api_key():
    """Delete the API key from the system keyring."""
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass

def get_file_content(file_path: Path) -> str | None:
    """Extract up to the first 2048 chars from supported file types."""
    try:
        if file_path.suffix == '.pdf':
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                content = ""
                for page in reader.pages:
                    content += page.extract_text() or ""
                    if len(content) > 2048:
                        break
                return content[:2048]
        elif file_path.suffix == '.docx':
            doc = docx.Document(file_path)
            content = "\n".join([para.text for para in doc.paragraphs])
            return content[:2048]
        elif file_path.suffix in ['.txt', '.md', '.py', '.js', '.html', '.css']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(2048)
        else:
            return None
    except Exception as e:
        logging.getLogger("organizer").error(f"Error reading '{file_path.name}': {e}")
        return None

def _get_unique_path(path: Path) -> Path:
    """Generate a unique file path if the destination already exists."""
    if not path.exists():
        return path
    
    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    counter = 1
    
    while True:
        new_name = f"{stem} ({counter}){suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1

def _collect_metadata(file: Path, is_content_mode: bool) -> dict:
    """Collect metadata to help AI classification.
    Returns: dict with object_file_type, file_size, file_type_extension, mime_type, and shortcut markers when applicable.
    """
    meta: dict = {}
    try:
        st = file.stat()
        size = st.st_size
        # Timestamps
        try:
            created_at = datetime.datetime.fromtimestamp(st.st_ctime, tz=datetime.timezone.utc).isoformat()
        except Exception:
            created_at = None
        try:
            modified_at = datetime.datetime.fromtimestamp(st.st_mtime, tz=datetime.timezone.utc).isoformat()
        except Exception:
            modified_at = None
    except Exception:
        size = None
        created_at = None
        modified_at = None

    ext = file.suffix.lower()
    mime, _ = mimetypes.guess_type(file.name)
    if not mime:
        # Valores razonables por defecto
        if ext == '.lnk':
            mime = 'application/x-ms-shortcut'
        else:
            mime = 'application/octet-stream'

    is_shortcut = ext == '.lnk'
    meta['object_file_type'] = 'shortcut' if is_shortcut else 'file'
    meta['file_size'] = size
    meta['file_type_extension'] = ext.lstrip('.')
    meta['mime_type'] = mime
    # Timestamps
    meta['created_at'] = created_at
    meta['modified_at'] = modified_at

    # Shortcut hints
    if is_shortcut:
        meta['is_shortcut'] = True
        meta['shortcut_base'] = file.stem
        
  
    return meta

def clean_artifacts(
    folder_path: Path,
    delete_log: bool = True,
    remove_empty_dirs: bool = True,
    log_callback: Callable | None = None,
):
    """Remove movement_log.json and/or empty subfolders within folder_path."""
    logger = logging.getLogger("organizer")

    if delete_log:
        log_file = folder_path / MOVEMENT_LOG_FILE
        if log_file.exists():
            try:
                log_file.unlink()
                logger.info("Movement log removed (movement_log.json).")
            except Exception as e:
                logger.info(f"Could not remove movement_log.json: {e}")
        else:
            logger.info("No movement_log.json found to delete.")

    if remove_empty_dirs:
        _remove_empty_category_folders(folder_path)


def classify_files(
    folder_path: Path,
    mode: str,
    categories: list[str],
    genai_client: genai.Client,
    model_name: str = "gemini-2.5-flash",
    thinking_budget: int | None = 0,
    ai_context: str | None = None,
    exclude_extensions: list[str] | None = None,
    exclude_files: list[str] | None = None,
    allow_ai_skip: bool = True,
):
    """Classify files with AI and return a list of {filename, category} objects.
    Does not move any files.
    """
    logger = logging.getLogger("organizer")
    logger.info("Preparing data for classification...")

    try:
        # Normalizar extensiones excluidas
        excluded_exts = set()
        if exclude_extensions:
            for ext in exclude_extensions:
                if not ext:
                    continue
                e = ext.strip().lower()
                if not e.startswith('.'):
                    e = '.' + e
                excluded_exts.add(e)

        all_files = [
            f for f in folder_path.iterdir() if f.is_file() and 
            f.name not in ["organizer.log", MOVEMENT_LOG_FILE, "config.json", ".env"] and
            not f.name.endswith(('.py', '.pyc'))
        ]

        files_to_process: list[Path] = []
        # Normalize excluded file patterns
        excluded_file_patterns = []
        if exclude_files:
            for p in exclude_files:
                p = (p or "").strip()
                if p:
                    excluded_file_patterns.append(p)
        for f in all_files:
            if f.suffix.lower() in excluded_exts:
                logger.info(f"Excluded by extension: '{f.name}'")
                continue
            # match against patterns or exact names (case-insensitive)
            excluded_by_name = False
            for patt in excluded_file_patterns:
                if fnmatch.fnmatch(f.name.lower(), patt.lower()) or f.name.lower() == patt.lower():
                    logger.info(f"Excluded by name/pattern: '{f.name}' matches '{patt}'")
                    excluded_by_name = True
                    break
            if excluded_by_name:
                continue
            files_to_process.append(f)

        if not files_to_process:
            logger.info("No files to classify in the selected folder.")
            return []

        logger.info(f"Found {len(files_to_process)} files to classify.")

        file_data = []
        is_content_mode = (mode == 'by_content')
        for file in files_to_process:
            item = {"filename": file.name}
            # metadatos comunes en ambos modos
            item.update(_collect_metadata(file, is_content_mode))
            if is_content_mode:
                content = get_file_content(file)
                if content:
                    item['content_snippet'] = content
            file_data.append(item)

        user_context = (ai_context or "").strip()
        skip_instruction = (
            'If the context or rules imply a file must NOT be moved, set its category to "SKIP" exactly.'
            if allow_ai_skip else
            'Do not skip files; always choose one of the provided categories.'
        )

        prompt = f"""
You are an expert file organizer. Classify the list of files into the provided categories.
User instructions/context (high priority, apply first): {user_context or "(none)"}

Current date: {datetime.datetime.now().isoformat()}

Rules:
- Return a single JSON object with a key "files" containing a list of objects: {{"filename": "...", "category": "..."}}.
- Categories must be chosen EXACTLY from the provided list below. Do not invent new categories.
- {skip_instruction}
- If a file doesn't fit any category, use "Misc".
- For Windows shortcuts (.lnk), classify based on the base name (field "shortcut_base") and not as a separate category.
- Consider metadata such as object_file_type, file_type_extension, mime_type, file_size, etc, and any content_snippet.

Available Categories: {json.dumps(categories, ensure_ascii=False)}
Files to classify:
{json.dumps(file_data, indent=2, ensure_ascii=False)}

Respond with JSON ONLY, no markdown fences.
        """

        #logger.info(f"Lista de nombres y metadatos de archivos:   {json.dumps(file_data, indent=2)}")
        logger.info("Sending request to Gemini API for classification...")
        # Llamada a la API con manejo robusto de errores usando el nuevo cliente
        try:
            config = None
            if thinking_budget is not None:
                config = genai_types.GenerateContentConfig(
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=thinking_budget)
                )
            response = genai_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            response_text = response.text if hasattr(response, 'text') else None
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return []

        if not response_text:
            logger.error("Gemini response does not contain usable text.")
            return []

        # Limpiar y parsear la respuesta JSON
        cleaned_response_text = response_text.strip().replace("```json", "").replace("```", "")
        logger.info("Response received. Processing classification...")

        try:
            classification = json.loads(cleaned_response_text)
            classified_files = classification.get("files", [])
        except json.JSONDecodeError:
            logger.error("Error: The AI response is not valid JSON.")
            logger.error(f"Received response: {cleaned_response_text}")
            return []

        return classified_files

    except Exception as e:
        logger.error(f"An unexpected error occurred during classification: {e}")
        return []


def plan_moves(
    folder_path: Path,
    classified_files: list[dict],
    allow_ai_skip: bool = True,
):
    """Generate a move plan without touching the disk.
    Returns a list of: {filename, category, action: 'move'|'skip'|'missing', destination?}
    """
    logger = logging.getLogger("organizer")
    plan: list[dict] = []
    for item in classified_files:
        filename = item.get("filename")
        category = item.get("category")
        if not filename or not category:
            continue

        # Respetar 'SKIP'
        if allow_ai_skip and isinstance(category, str) and category.strip().upper() == "SKIP":
            plan.append({
                "filename": filename,
                "category": category,
                "action": "skip",
            })
            continue

        source_path = folder_path / filename
        if not source_path.exists():
            logger.warning(f"Not found for preview: '{filename}'")
            plan.append({
                "filename": filename,
                "category": category,
                "action": "missing",
            })
            continue

        category_folder = folder_path / category
        destination_path = _get_unique_path(category_folder / filename)
        plan.append({
            "filename": filename,
            "category": category,
            "action": "move",
            "destination": str(destination_path),
        })

    return plan


def preview_classification_and_plan(
    folder_path: Path,
    mode: str,
    categories: list[str],
    genai_client: genai.Client,
    model_name: str = "gemini-2.5-flash",
    thinking_budget: int | None = 0,
    ai_context: str | None = None,
    exclude_extensions: list[str] | None = None,
    exclude_files: list[str] | None = None,
    allow_ai_skip: bool = True,
):
    """Get classification and a move plan without moving files."""
    classified = classify_files(
        folder_path=folder_path,
        mode=mode,
        categories=categories,
        genai_client=genai_client,
        model_name=model_name,
        thinking_budget=thinking_budget,
        ai_context=ai_context,
        exclude_extensions=exclude_extensions,
        exclude_files=exclude_files,
        allow_ai_skip=allow_ai_skip,
    )
    plan = plan_moves(folder_path, classified, allow_ai_skip=allow_ai_skip)
    return classified, plan


def batch_classify_and_move(
    folder_path: Path,
    mode: str,
    categories: list[str],
    log_callback: Callable,
    genai_client: genai.Client,
    model_name: str = "gemini-2.5-flash",
    thinking_budget: int | None = 0,
    ai_context: str | None = None,
    exclude_extensions: list[str] | None = None,
    exclude_files: list[str] | None = None,
    allow_ai_skip: bool = True,
):
    """Classify and move files in batch using Gemini AI."""
    logger = logging.getLogger("organizer")
    logger.info("Starting organization...")

    classified_files = classify_files(
        folder_path=folder_path,
        mode=mode,
        categories=categories,
        genai_client=genai_client,
        model_name=model_name,
        thinking_budget=thinking_budget,
        ai_context=ai_context,
        exclude_extensions=exclude_extensions,
        exclude_files=exclude_files,
        allow_ai_skip=allow_ai_skip,
    )

    if not classified_files:
        logger.info("No classification results. Nothing to move.")
        return

    movement_log: list[dict] = []
    for item in classified_files:
        filename = item.get("filename")
        category = item.get("category")
        if not filename or not category:
            continue

        if allow_ai_skip and isinstance(category, str) and category.strip().upper() == "SKIP":
            logger.info(f"Skipped by AI: '{filename}'")
            continue

        source_path = folder_path / filename
        if not source_path.exists():
            logger.warning(f"Classified file '{filename}' was not found in the folder.")
            continue

        category_folder = folder_path / category
        category_folder.mkdir(exist_ok=True)
        destination_path = _get_unique_path(category_folder / filename)

        try:
            shutil.move(str(source_path), str(destination_path))
            log_entry = {
                "source": str(source_path),
                "destination": str(destination_path)
            }
            movement_log.append(log_entry)
            logger.info(f"Moved: '{filename}' -> '{category}'")
        except Exception as e:
            logger.error(f"Could not move '{filename}': {e}")

    log_path = folder_path / MOVEMENT_LOG_FILE
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(movement_log, f, indent=4, ensure_ascii=False)

    logger.info("Organization completed.")


def apply_plan(
    folder_path: Path,
    plan: list[dict],
    log_callback: Callable | None = None,
):
    """Apply a precomputed move plan.
    Only executes entries with action == 'move'. Writes movement_log.json for completed moves.
    """
    logger = logging.getLogger("organizer")

    movement_log: list[dict] = []
    for item in plan:
        if item.get("action") != "move":
            continue
        filename = item.get("filename")
        category = item.get("category")
        if not filename or not category:
            continue
        source_path = folder_path / filename
        if not source_path.exists():
            logger.info(f"File not found to move: '{filename}'")
            continue
        category_folder = folder_path / str(category)
        category_folder.mkdir(exist_ok=True)
        # Recalcular destino único por si cambió el estado del disco
        destination_path = _get_unique_path(category_folder / filename)
        try:
            shutil.move(str(source_path), str(destination_path))
            movement_log.append({
                "source": str(source_path),
                "destination": str(destination_path),
            })
            logger.info(f"Moved: '{filename}' -> '{category}'")
        except Exception as e:
            logger.info(f"Could not move '{filename}': {e}")

    log_path = folder_path / MOVEMENT_LOG_FILE
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(movement_log, f, indent=4, ensure_ascii=False)

    logger.info("Plan application completed.")


def revert_changes(folder_path: Path, log_callback: Callable):
    """Revert the last file organization operation."""
    logger = logging.getLogger("organizer")
    log_file = folder_path / MOVEMENT_LOG_FILE

    if not log_file.exists():
        logger.info("Movement log not found. Nothing to revert.")
        return

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            movement_log = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        logger.warning("Movement log is empty or corrupted. Cannot revert.")
        movement_log = []

    if not movement_log:
        logger.info("No recorded movements to revert.")
        return

    logger.info("Starting revert...")
    for movement in reversed(movement_log):
        source_str = movement.get("source")
        destination_str = movement.get("destination")

        if not source_str or not destination_str:
            continue

        source_path = Path(source_str)
        destination_path = Path(destination_str)

        try:
            if destination_path.exists():
                if source_path.exists():
                    logger.warning(f"Source file already exists and will not be overwritten: '{source_path}'. Skipping this move.")
                    continue
                # Asegurar que el directorio de destino original exista
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination_path), str(source_path))
                logger.info(f"Reverted: '{destination_path.name}' -> '{source_path.parent.name}'")
            else:
                logger.warning(f"Could not find file '{destination_path.name}' to revert.")
        except Exception as e:
            logger.error(f"Could not revert move of '{destination_path.name}': {e}")

    # Empty the log file after a successful revert
    with open(log_file, 'w') as f:
        f.write("[]")
    
    # Clean empty category folders
    _remove_empty_category_folders(folder_path)

    logger.info("Revert completed.")


def _remove_empty_category_folders(base_folder: Path):
    """Delete empty subfolders inside the base folder (empty categories)."""
    logger = logging.getLogger("organizer")
    try:
        for child in base_folder.iterdir():
            if child.is_dir():
                try:
                    # Si está vacía, eliminar
                    if not any(child.iterdir()):
                        child.rmdir()
                        logger.info(f"Removed empty category folder: '{child.name}'")
                except Exception as e:
                    logger.warning(f"Could not remove folder '{child}': {e}")
    except Exception as e:
        logger.warning(f"Could not scan folders for cleanup in '{base_folder}': {e}")

