"""Minimal bencode encoder/decoder (BEP 3).

Strings stay `bytes`; callers decode the ones they know are text. `decode`
also returns the raw byte span of the top-level `info` dict so the v1
infohash can be computed from the exact original bytes.
"""

from __future__ import annotations

from typing import Any, Union

Bencodable = Union[int, bytes, str, list[Any], dict[Any, Any]]


class BencodeError(ValueError):
    pass


def decode(data: bytes) -> Any:
    """Decode a complete bencoded value.

    >>> decode(b"d3:cow3:moo4:spaml1:a1:bee")
    {b'cow': b'moo', b'spam': [b'a', b'b']}
    >>> decode(b"i-42e")
    -42
    """
    value, end = _decode(data, 0)
    if end != len(data):
        raise BencodeError(f"trailing data at byte {end}")
    return value


def info_span(data: bytes) -> tuple[int, int]:
    """Byte span [start, end) of the top-level dict's `info` value.

    >>> raw = b"d8:announce3:url4:infod4:name1:xee"
    >>> s, e = info_span(raw); raw[s:e]
    b'd4:name1:xe'
    """
    if not data.startswith(b"d"):
        raise BencodeError("not a dictionary")
    i = 1
    while data[i : i + 1] != b"e":
        key, i = _decode_bytes(data, i)
        start = i
        _, i = _decode(data, i)
        if key == b"info":
            return start, i
    raise BencodeError("no info dictionary")


def encode(value: Bencodable) -> bytes:
    """Encode a value; dict keys are sorted as BEP 3 requires.

    >>> encode({"b": 1, "a": [b"x", "y"]})
    b'd1:al1:x1:ye1:bi1ee'
    """
    if isinstance(value, bool):
        raise BencodeError("booleans are not bencodable")
    if isinstance(value, int):
        return b"i%de" % value
    if isinstance(value, str):
        value = value.encode()
    if isinstance(value, bytes):
        return b"%d:%s" % (len(value), value)
    if isinstance(value, list):
        return b"l" + b"".join(encode(v) for v in value) + b"e"
    if isinstance(value, dict):
        items = sorted(((k.encode() if isinstance(k, str) else k), v) for k, v in value.items())
        return b"d" + b"".join(encode(k) + encode(v) for k, v in items) + b"e"
    raise BencodeError(f"cannot encode {type(value).__name__}")


def _decode(data: bytes, i: int) -> tuple[Any, int]:
    if i >= len(data):
        raise BencodeError("unexpected end of data")
    lead = data[i : i + 1]
    if lead == b"i":
        end = data.index(b"e", i)
        try:
            return int(data[i + 1 : end]), end + 1
        except ValueError as exc:
            raise BencodeError(f"bad integer at {i}") from exc
    if lead == b"l":
        i += 1
        items = []
        while data[i : i + 1] != b"e":
            item, i = _decode(data, i)
            items.append(item)
        return items, i + 1
    if lead == b"d":
        i += 1
        result: dict[bytes, Any] = {}
        while data[i : i + 1] != b"e":
            key, i = _decode_bytes(data, i)
            result[key], i = _decode(data, i)
        return result, i + 1
    if lead.isdigit():
        return _decode_bytes(data, i)
    raise BencodeError(f"invalid token {lead!r} at {i}")


def _decode_bytes(data: bytes, i: int) -> tuple[bytes, int]:
    colon = data.index(b":", i)
    try:
        length = int(data[i:colon])
    except ValueError as exc:
        raise BencodeError(f"bad string length at {i}") from exc
    start = colon + 1
    end = start + length
    if end > len(data):
        raise BencodeError("string runs past end of data")
    return data[start:end], end
