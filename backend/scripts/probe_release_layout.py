"""Read a remote zip's central directory via HTTP Range (no full download).

Determines the exact file layout of MAA release packages.
"""
import struct
import sys

import httpx

ZIP_EOCD_SIG = b"PK\x05\x06"
ZIP_CENTRAL_SIG = b"PK\x01\x02"


def fetch_range(client: httpx.Client, url: str, start: int, end: int) -> bytes:
    resp = client.get(url, headers={"Range": f"bytes={start}-{end}"})
    resp.raise_for_status()
    return resp.content


def zip_listing(url: str, tail_bytes: int = 4 * 1024 * 1024) -> list[str]:
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        head = client.head(url)
        head.raise_for_status()
        total = int(head.headers.get("content-length", 0))
        print(f"total size: {total:,} bytes")
        if total == 0:
            raise SystemExit("no content-length")

        tail = fetch_range(client, url, max(0, total - tail_bytes), total - 1)
        eocd_at = tail.rfind(ZIP_EOCD_SIG)
        if eocd_at < 0:
            raise SystemExit("EOCD not found in tail")
        eocd = tail[eocd_at : eocd_at + 22]
        (_, _, _, _, _, cd_size, cd_offset, _) = struct.unpack("<4s4H2LH", eocd)

        cd = b""
        pos = 0
        while pos < cd_size:
            end = min(pos + 512 * 1024, cd_size)
            chunk = fetch_range(client, url, cd_offset + pos, cd_offset + end - 1)
            cd += chunk
            pos += len(chunk)

        names: list[str] = []
        idx = 0
        while idx + 46 <= len(cd):
            if cd[idx : idx + 4] != ZIP_CENTRAL_SIG:
                break
            (
                _, _, _, _, _, _, _, _, _, _, nlen, elen, clen, _, _, _, _,
            ) = struct.unpack("<4s6H3L5H2L", cd[idx : idx + 46])
            name = cd[idx + 46 : idx + 46 + nlen].decode("utf-8", errors="replace")
            names.append(name)
            idx += 46 + nlen + elen + clen
        return names


def summarize(names: list[str]) -> None:
    print(f"\n{len(names)} entries, top-level dirs:")
    tops: dict[str, int] = {}
    for n in names:
        top = n.split("/")[0]
        tops[top] = tops.get(top, 0) + 1
    for k, v in sorted(tops.items()):
        print(f"  {k}/  ({v})")

    print("\nengine/resource-relevant entries:")
    seen = set()
    for n in names:
        low = n.lower()
        if low.endswith((".dll", ".so", ".exe")) or n.split("/")[-1] == "sample.py":
            if low not in seen:
                seen.add(low)
                print(" ", n)


if __name__ == "__main__":
    url = sys.argv[1]
    summarize(zip_listing(url))
