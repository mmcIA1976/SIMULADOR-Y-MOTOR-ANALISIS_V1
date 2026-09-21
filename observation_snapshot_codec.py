"""Lossless, bounded storage for repeated observational rule evidence.

Only the already-compacted rule traces are encoded. Probabilities, horizons
and version contracts remain queryable JSON; no raw market arrays are added.
Readers also accept the historical, unencoded trace dictionary.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import zlib


TRACE_ENCODING = "zlib-base64-json-v1"
MAX_EXPANDED_TRACE_BYTES = 256_000
MAX_ENCODED_TRACE_BYTES = 48_000


def pack_rule_traces(traces: dict) -> dict:
    raw = json.dumps(
        traces, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(raw) > MAX_EXPANDED_TRACE_BYTES:
        raise ValueError("observation_rule_traces_too_large")
    if len(raw) < 1024:
        return traces
    encoded = {
        "encoding": TRACE_ENCODING,
        "uncompressed_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "data": base64.b64encode(zlib.compress(raw, level=9)).decode("ascii"),
    }
    encoded_size = len(json.dumps(encoded, separators=(",", ":")).encode())
    return encoded if encoded_size < len(raw) else traces


def snapshot_rule_traces(snapshot: dict) -> dict:
    """Decode exact evidence, rejecting corrupt/oversized records explicitly."""
    traces = snapshot.get("stage_rule_traces")
    if not isinstance(traces, dict):
        return {}
    if "encoding" not in traces:
        return traces
    if traces.get("encoding") != TRACE_ENCODING:
        raise ValueError("observation_rule_trace_encoding_unsupported")
    try:
        declared = traces["uncompressed_bytes"]
        data = traces["data"]
        if (
            type(declared) is not int
            or not 0 < declared <= MAX_EXPANDED_TRACE_BYTES
            or not isinstance(data, str)
            or len(data) > MAX_ENCODED_TRACE_BYTES
        ):
            raise ValueError("invalid_size")
        compressed = base64.b64decode(data, validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, MAX_EXPANDED_TRACE_BYTES + 1)
        if (
            len(raw) != declared
            or len(raw) > MAX_EXPANDED_TRACE_BYTES
            or not decoder.eof
            or decoder.unused_data
            or decoder.unconsumed_tail
            or hashlib.sha256(raw).hexdigest() != traces.get("sha256")
        ):
            raise ValueError("invalid_content")
        decoded = json.loads(raw)
        if not isinstance(decoded, dict) or not all(
            isinstance(items, list)
            and all(isinstance(item, dict) for item in items)
            for items in decoded.values()
        ):
            raise ValueError("invalid_traces")
        return decoded
    except (KeyError, TypeError, ValueError, binascii.Error, zlib.error) as exc:
        raise ValueError("observation_rule_trace_payload_invalid") from exc
