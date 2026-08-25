"""Secure local credentials for the AI.INPUT.IM Personal xbar probe.

The browser stores the site's session in local storage.  Personal xbar uses a
separate, deliberately small credential record in the user's login keychain so
the quota probe can run without a browser.  This module never prints or places
the token values in process arguments.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Protocol

KEYCHAIN_SERVICE = os.environ.get(
    "AI_INPUT_KEYCHAIN_SERVICE", "skillctl.personal-xbar.ai-input-auth"
)
KEYCHAIN_ACCOUNT = os.environ.get(
    "AI_INPUT_KEYCHAIN_ACCOUNT", "subscriptions"
)
TOKEN_MAX_LENGTH = 128 * 1024
DEFAULT_REFRESH_LEAD_SECONDS = 120


class AuthError(RuntimeError):
    """A credential operation failed without exposing its secret values."""


class MissingCredentials(AuthError):
    """No local AI.INPUT.IM credentials have been configured."""


class KeychainUnavailable(AuthError):
    """The macOS login keychain cannot be reached by this process."""


class KeychainStore(Protocol):
    def read(self) -> str | None: ...

    def write(self, value: str) -> None: ...

    def delete(self) -> None: ...


@dataclass(frozen=True, repr=False)
class AiInputCredentials:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: int | None = None

    def __repr__(self) -> str:
        expiry = self.expires_at if self.expires_at is not None else "unknown"
        return f"AiInputCredentials(access_token=<redacted>, refresh_token=<redacted>, expires_at={expiry!r})"


def _token_value(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AuthError(f"{label} is missing")
    token = value.strip()
    if not token:
        raise AuthError(f"{label} is empty")
    if len(token) > TOKEN_MAX_LENGTH:
        raise AuthError(f"{label} is too long")
    return token


def jwt_expiry(token: str) -> int | None:
    """Read a JWT exp claim locally; opaque access tokens simply return None."""

    parts = token.split(".")
    if len(parts) != 3 or len(parts[1]) > TOKEN_MAX_LENGTH:
        return None
    try:
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        raw = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("exp")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    expiry = int(value)
    return expiry if expiry > 0 else None


def make_credentials(
    access_token: object,
    refresh_token: object,
    expires_at: object = None,
) -> AiInputCredentials:
    access = _token_value(access_token, "access token")
    refresh = _token_value(refresh_token, "refresh token")
    expiry: int | None
    if expires_at is None or expires_at == "":
        expiry = jwt_expiry(access)
    elif isinstance(expires_at, bool) or not isinstance(expires_at, (int, float, str)):
        raise AuthError("access token expiry is invalid")
    else:
        try:
            expiry = int(float(expires_at))
        except (TypeError, ValueError, OverflowError):
            raise AuthError("access token expiry is invalid") from None
        if expiry <= 0:
            expiry = None
    return AiInputCredentials(access, refresh, expiry)


def credentials_payload(credentials: AiInputCredentials) -> dict[str, object]:
    return {
        "access_token": credentials.access_token,
        "refresh_token": credentials.refresh_token,
        "expires_at": credentials.expires_at,
    }


def credentials_json(credentials: AiInputCredentials) -> str:
    return json.dumps(
        credentials_payload(credentials), separators=(",", ":"), sort_keys=True
    )


def credentials_from_json(value: str) -> AiInputCredentials:
    if len(value.encode("utf-8", errors="ignore")) > TOKEN_MAX_LENGTH * 2:
        raise AuthError("stored credential record is too large")
    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        raise AuthError("stored credential record is invalid") from None
    if not isinstance(raw, dict):
        raise AuthError("stored credential record is invalid")
    return make_credentials(
        raw.get("access_token"), raw.get("refresh_token"), raw.get("expires_at")
    )


def credentials_need_refresh(
    credentials: AiInputCredentials,
    now_epoch: int,
    lead_seconds: int = DEFAULT_REFRESH_LEAD_SECONDS,
) -> bool:
    return (
        credentials.expires_at is not None
        and credentials.expires_at <= now_epoch + max(0, lead_seconds)
    )


def credentials_summary(
    credentials: AiInputCredentials | None,
    now_epoch: int,
) -> dict[str, object]:
    if credentials is None:
        return {"configured": False, "has_access_token": False, "has_refresh_token": False}
    expiry = credentials.expires_at
    return {
        "configured": True,
        "has_access_token": True,
        "has_refresh_token": True,
        "expires_at": expiry,
        "expires_in": expiry - now_epoch if expiry is not None else None,
        "refresh_due": credentials_need_refresh(credentials, now_epoch),
    }


class _CFDictionaryKeyCallBacks(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_long),
        ("retain", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("copyDescription", ctypes.c_void_p),
        ("equal", ctypes.c_void_p),
        ("hash", ctypes.c_void_p),
    ]


class _CFDictionaryValueCallBacks(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_long),
        ("retain", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("copyDescription", ctypes.c_void_p),
        ("equal", ctypes.c_void_p),
    ]


class MacOSKeychainStore:
    """A generic-password item backed by Security.framework."""

    def __init__(self, service: str = KEYCHAIN_SERVICE, account: str = KEYCHAIN_ACCOUNT):
        if sys.platform != "darwin":
            raise KeychainUnavailable("AI.INPUT.IM keychain requires macOS")
        self.service = _token_value(service, "keychain service")
        self.account = _token_value(account, "keychain account")
        try:
            self._security = ctypes.CDLL(
                "/System/Library/Frameworks/Security.framework/Security"
            )
            self._core_foundation = ctypes.CDLL(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
            )
            self._configure_bindings()
        except (AttributeError, OSError, TypeError) as error:
            raise KeychainUnavailable("macOS keychain bindings are unavailable") from error

    def _configure_bindings(self) -> None:
        cf = self._core_foundation
        sec = self._security
        self._cf_string = cf.CFStringCreateWithCString
        self._cf_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        self._cf_string.restype = ctypes.c_void_p
        self._cf_data = cf.CFDataCreate
        self._cf_data.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        self._cf_data.restype = ctypes.c_void_p
        self._cf_release = cf.CFRelease
        self._cf_release.argtypes = [ctypes.c_void_p]
        self._cf_release.restype = None
        self._cf_data_length = cf.CFDataGetLength
        self._cf_data_length.argtypes = [ctypes.c_void_p]
        self._cf_data_length.restype = ctypes.c_long
        self._cf_data_bytes = cf.CFDataGetBytePtr
        self._cf_data_bytes.argtypes = [ctypes.c_void_p]
        self._cf_data_bytes.restype = ctypes.POINTER(ctypes.c_ubyte)
        self._cf_dictionary_create = cf.CFDictionaryCreate
        self._cf_dictionary_create.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_long,
            ctypes.POINTER(_CFDictionaryKeyCallBacks),
            ctypes.POINTER(_CFDictionaryValueCallBacks),
        ]
        self._cf_dictionary_create.restype = ctypes.c_void_p
        self._key_callbacks = _CFDictionaryKeyCallBacks.in_dll(
            cf, "kCFTypeDictionaryKeyCallBacks"
        )
        self._value_callbacks = _CFDictionaryValueCallBacks.in_dll(
            cf, "kCFTypeDictionaryValueCallBacks"
        )

        self._sec_copy_matching = sec.SecItemCopyMatching
        self._sec_copy_matching.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._sec_copy_matching.restype = ctypes.c_int32
        self._sec_add = sec.SecItemAdd
        self._sec_add.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self._sec_add.restype = ctypes.c_int32
        self._sec_update = sec.SecItemUpdate
        self._sec_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._sec_update.restype = ctypes.c_int32
        self._sec_delete = sec.SecItemDelete
        self._sec_delete.argtypes = [ctypes.c_void_p]
        self._sec_delete.restype = ctypes.c_int32

        def constant(name: str) -> ctypes.c_void_p:
            return ctypes.c_void_p.in_dll(sec, name)

        self._k_sec_class = constant("kSecClass")
        self._k_sec_class_generic = constant("kSecClassGenericPassword")
        self._k_sec_attr_service = constant("kSecAttrService")
        self._k_sec_attr_account = constant("kSecAttrAccount")
        self._k_sec_value_data = constant("kSecValueData")
        self._k_sec_return_data = constant("kSecReturnData")
        self._k_sec_match_limit = constant("kSecMatchLimit")
        self._k_sec_match_limit_one = constant("kSecMatchLimitOne")
        self._k_cf_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        self._k_cf_false = ctypes.c_void_p.in_dll(cf, "kCFBooleanFalse")

    def _string(self, value: str) -> ctypes.c_void_p:
        pointer = self._cf_string(None, value.encode("utf-8"), 0x08000100)
        if not pointer:
            raise KeychainUnavailable("could not create keychain value")
        return ctypes.c_void_p(pointer)

    def _data(self, value: bytes) -> ctypes.c_void_p:
        buffer = ctypes.create_string_buffer(value)
        pointer = self._cf_data(None, buffer, len(value))
        if not pointer:
            raise KeychainUnavailable("could not create keychain data")
        return ctypes.c_void_p(pointer)

    def _dictionary(
        self,
        values: list[tuple[ctypes.c_void_p, ctypes.c_void_p]],
    ) -> ctypes.c_void_p:
        keys = (ctypes.c_void_p * len(values))(*[key.value for key, _ in values])
        objects = (ctypes.c_void_p * len(values))(
            *[value.value for _, value in values]
        )
        pointer = self._cf_dictionary_create(
            None,
            keys,
            objects,
            len(values),
            ctypes.byref(self._key_callbacks),
            ctypes.byref(self._value_callbacks),
        )
        if not pointer:
            raise KeychainUnavailable("could not create keychain query")
        return ctypes.c_void_p(pointer)

    def _release(self, pointer: ctypes.c_void_p | None) -> None:
        if pointer is not None and pointer.value:
            self._cf_release(pointer)

    def _base_values(self) -> list[tuple[ctypes.c_void_p, ctypes.c_void_p]]:
        return [
            (self._k_sec_class, self._k_sec_class_generic),
            (self._k_sec_attr_service, self._string(self.service)),
            (self._k_sec_attr_account, self._string(self.account)),
        ]

    def read(self) -> str | None:
        values = self._base_values()
        query = self._dictionary(
            values
            + [
                (self._k_sec_return_data, self._k_cf_true),
                (self._k_sec_match_limit, self._k_sec_match_limit_one),
            ]
        )
        result = ctypes.c_void_p()
        try:
            status = self._sec_copy_matching(query, ctypes.byref(result))
            if status == -25300:
                return None
            if status != 0 or not result.value:
                raise KeychainUnavailable(f"keychain read failed ({status})")
            length = int(self._cf_data_length(result))
            if length < 0 or length > TOKEN_MAX_LENGTH * 2:
                raise KeychainUnavailable("stored keychain value is too large")
            pointer = self._cf_data_bytes(result)
            if not pointer:
                raise KeychainUnavailable("stored keychain value is empty")
            return ctypes.string_at(pointer, length).decode("utf-8")
        except UnicodeDecodeError as error:
            raise KeychainUnavailable("stored keychain value is not UTF-8") from error
        finally:
            self._release(result)
            self._release(query)
            for _, value in values[1:3]:
                self._release(value)

    def write(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > TOKEN_MAX_LENGTH * 2:
            raise AuthError("credential record is too large")
        base_values = self._base_values()
        data = self._data(encoded)
        query = self._dictionary(base_values)
        attributes = self._dictionary([(self._k_sec_value_data, data)])
        try:
            status = self._sec_update(query, attributes)
            if status == -25300:
                add_values = base_values + [(self._k_sec_value_data, data)]
                add_query = self._dictionary(add_values)
                try:
                    status = self._sec_add(add_query, None)
                finally:
                    self._release(add_query)
            if status == -25299:
                # Another xbar invocation inserted it between update and add.
                status = self._sec_update(query, attributes)
            if status != 0:
                raise KeychainUnavailable(f"keychain write failed ({status})")
        finally:
            self._release(attributes)
            self._release(query)
            self._release(data)
            for _, value in base_values[1:3]:
                self._release(value)

    def delete(self) -> None:
        values = self._base_values()
        query = self._dictionary(values)
        try:
            status = self._sec_delete(query)
            if status not in (0, -25300):
                raise KeychainUnavailable(f"keychain delete failed ({status})")
        finally:
            self._release(query)
            for _, value in values[1:3]:
                self._release(value)


def default_keychain_store() -> KeychainStore:
    return MacOSKeychainStore()


def read_credentials(store: KeychainStore | None = None) -> AiInputCredentials | None:
    active_store = store or default_keychain_store()
    raw = active_store.read()
    if raw is None:
        return None
    return credentials_from_json(raw)


def write_credentials(
    credentials: AiInputCredentials,
    store: KeychainStore | None = None,
) -> None:
    active_store = store or default_keychain_store()
    active_store.write(credentials_json(credentials))


def delete_credentials(store: KeychainStore | None = None) -> None:
    active_store = store or default_keychain_store()
    active_store.delete()


def require_credentials(store: KeychainStore | None = None) -> AiInputCredentials:
    credentials = read_credentials(store)
    if credentials is None:
        raise MissingCredentials("AI.INPUT.IM credentials are not configured")
    return credentials


__all__ = [
    "AiInputCredentials",
    "AuthError",
    "DEFAULT_REFRESH_LEAD_SECONDS",
    "KEYCHAIN_ACCOUNT",
    "KEYCHAIN_SERVICE",
    "KeychainStore",
    "KeychainUnavailable",
    "MacOSKeychainStore",
    "MissingCredentials",
    "credentials_from_json",
    "credentials_json",
    "credentials_need_refresh",
    "credentials_payload",
    "credentials_summary",
    "default_keychain_store",
    "delete_credentials",
    "jwt_expiry",
    "make_credentials",
    "read_credentials",
    "require_credentials",
    "write_credentials",
]
