"""Windows DPAPI-backed storage for the dyjie.net login."""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import json
import os
from pathlib import Path


_MAGIC = b"MOVIEPOSTER-DYJIE-DPAPI-1\n"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _crypt(data: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is required for credential storage")
    if not data:
        raise ValueError("credential payload must not be empty")

    crypt32 = ctypes.WinDLL("Crypt32.dll")
    kernel32 = ctypes.WinDLL("Kernel32.dll")
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_buffer = ctypes.create_string_buffer(data)
    input_blob = _DataBlob(
        len(data),
        ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    output_blob = _DataBlob()
    if not function(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def save_credentials(path: Path, email: str, password: str) -> None:
    """Save credentials encrypted for the current Windows user."""
    email = str(email or "").strip()
    password = str(password or "")
    if not email or not password:
        raise ValueError("email and password are required")
    payload = json.dumps(
        {"email": email, "password": password},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.b64encode(_crypt(payload, True))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_bytes(_MAGIC + encoded)
    os.replace(temp_path, path)


def load_credentials(path: Path) -> tuple[str, str] | None:
    """Load credentials without exposing them to callers that only need presence."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        if not raw.startswith(_MAGIC):
            return None
        payload = _crypt(base64.b64decode(raw[len(_MAGIC) :]), False)
        data = json.loads(payload.decode("utf-8"))
        email = str(data.get("email") or "").strip()
        password = str(data.get("password") or "")
        return (email, password) if email and password else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeError):
        return None


def clear_credentials(path: Path) -> None:
    """Remove the encrypted credential record if it exists."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
