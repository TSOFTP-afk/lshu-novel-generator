from __future__ import annotations

import base64
import ctypes
import logging
import os
from ctypes import wintypes

logger = logging.getLogger(__name__)

DPAPI_PREFIX = "dpapi:"
_APP_ENTROPY = b"LingShuNovel-v1.3"


def protect_secret(secret: str) -> str:
    if not secret:
        return ""
    if os.name != "nt":
        logger.warning("DPAPI is only available on Windows, secret stored as plaintext")
        return secret
    return f"{DPAPI_PREFIX}{base64.b64encode(_crypt_protect(secret.encode('utf-8'), _APP_ENTROPY)).decode('ascii')}"


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(DPAPI_PREFIX):
        return value
    if os.name != "nt":
        logger.warning("DPAPI is only available on Windows, cannot decrypt secret")
        return ""
    payload = base64.b64decode(value[len(DPAPI_PREFIX) :].encode("ascii"))
    return _crypt_unprotect(payload, _APP_ENTROPY).decode("utf-8")


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(wintypes.BYTE)),
    ]


def _make_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE)))
    return blob, buffer


def _crypt_protect(data: bytes, entropy: bytes | None = None) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    in_blob, _buffer = _make_blob(data)
    entropy_blob = None
    entropy_buffer = None
    if entropy:
        entropy_blob, entropy_buffer = _make_blob(entropy)
    out_blob = _DataBlob()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob) if entropy_blob else None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, wintypes.HLOCAL))


def _crypt_unprotect(data: bytes, entropy: bytes | None = None) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    in_blob, _buffer = _make_blob(data)
    entropy_blob = None
    entropy_buffer = None
    if entropy:
        entropy_blob, entropy_buffer = _make_blob(entropy)
    out_blob = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob) if entropy_blob else None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, wintypes.HLOCAL))
