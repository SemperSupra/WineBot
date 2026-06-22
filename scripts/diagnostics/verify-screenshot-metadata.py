#!/usr/bin/env python3
# EXECUTION: HOST — reads session screenshot files; pure file validation
import argparse
import json
import struct
import sys
import zlib


REQUIRED_KEYS = [
    "winebot_request_id",
    "winebot_timestamp_unix",
    "winebot_timestamp_utc",
    "winebot_user_tag",
    "winebot_window_id",
    "winebot_window_title",
]


def read_png_text(path):
    meta = {}
    with open(path, "rb") as f:
        sig = f.read(8)
        if sig != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not png")
        while True:
            data = f.read(8)
            if len(data) < 8:
                break
            length, ctype = struct.unpack(">I4s", data)
            chunk = f.read(length)
            f.read(4)
            ctype = ctype.decode("ascii")
            if ctype == "tEXt":
                key, value = chunk.split(b"\x00", 1)
                meta[key.decode()] = value.decode(errors="replace")
            elif ctype == "zTXt":
                key, rest = chunk.split(b"\x00", 1)
                comp_data = rest[1:]
                try:
                    meta[key.decode()] = zlib.decompress(comp_data).decode(
                        errors="replace"
                    )
                except Exception:
                    pass
            if ctype == "IEND":
                break
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, dest="json_path")
    parser.add_argument("--req-id", required=True, dest="req_id")
    parser.add_argument("--tag", required=True, dest="tag")
    args = parser.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("request_id") != args.req_id:
        print("request_id mismatch", data.get("request_id"), args.req_id)
        return 1
    if data.get("user_tag") != args.tag:
        print("user_tag mismatch", data.get("user_tag"))
        return 1

    png_path = args.json_path[:-5] if args.json_path.endswith(".json") else None
    if not png_path:
        print("invalid json path")
        return 1

    meta = read_png_text(png_path)
    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        print("missing keys", missing)
        return 1
    if meta.get("winebot_request_id") != args.req_id:
        print("png request_id mismatch", meta.get("winebot_request_id"), args.req_id)
        return 1
    if meta.get("winebot_user_tag") != args.tag:
        print("png user_tag mismatch", meta.get("winebot_user_tag"))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
