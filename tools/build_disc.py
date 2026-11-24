#!/usr/bin/env python3
"""
Build a Thai game disc that differs from the original in exactly 2 files.

Old way (full-rebuild.bat): unpack every asset (~4 GB), recompress all 881
files, re-zip 1 GB. Slow, needs ~8 GB free, and every asset in the game
(animations, maps, ...) comes out different from the original.

This way:
  1. pull only the 2 files the mod changes out of the original disc (7za)
       resource/message/ichigo_message_all_US.lzs   (game text)
       resource/ui/font_data.lzs                     (fonts)
  2. decompress them (quickbms, same script the toolkit uses)
  3. unpack the archives, add Thai text + fonts (install_thai.py)
  4. repack the archives (128-byte aligned, like the original)
  5. recompress them (quickbms) and check they decode back byte-for-byte
  6. write the new disc: the other 879 entries are copied raw from the
     original (still encrypted, byte-identical); only the 2 files are new.

Usage:  py -3 build_disc.py --toolkit <toolkit folder> --original <disc> --out <new disc>
"""
import argparse, os, shutil, struct, subprocess, sys, time, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import install_thai as it  # noqa: E402

TARGETS = [
    ("resource/message/ichigo_message_all_US.lzs", it.MSG_REL),
    ("resource/ui/font_data.lzs", it.FONT_REL),
]
ALIGN = 128


def log(*a):
    print(*a, flush=True)


def run(cmd, stdin=None, cwd=None):
    r = subprocess.run(cmd, stdin=stdin, cwd=cwd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        sys.exit("Command failed:\n" + " ".join(cmd) + "\n" + (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:])
    return r


# ------------------------------------------------------------------ archive (.lzs.dcmp)
# u16 count (shares bytes with entry 0), then 64-byte entries:
#   u16, u16, u32 offset, u32 size, u32 id, char name[0x30]
def arc_read(data):
    n = struct.unpack_from("<H", data, 0)[0]
    ents = []
    for i in range(n):
        o = i * 64
        off, size = struct.unpack_from("<II", data, o + 4)
        name = data[o + 16:o + 64].split(b"\0")[0].decode("ascii")
        ents.append({"i": i, "off": off, "size": size, "name": name})
    return ents


def arc_write(orig, ents, files):
    """Rebuild: original table, files in original offset order, each 128-aligned."""
    order = sorted(ents, key=lambda e: e["off"])
    first = order[0]["off"]
    out = bytearray(orig[:first])
    for e in order:
        pad = (-len(out)) % ALIGN
        out += b"\0" * pad
        body = files[e["name"]]
        struct.pack_into("<II", out, e["i"] * 64 + 4, len(out), len(body))
        out += body
    out += b"\0" * ((-len(out)) % ALIGN)
    return bytes(out)


# ------------------------------------------------------------------ zip (stored entries only)
def zip_entries(path):
    f = open(path, "rb")
    f.seek(0, 2)
    end = f.tell()
    f.seek(max(0, end - 66000))
    tail = f.read()
    k = tail.rfind(b"PK\x05\x06")
    if k < 0:
        sys.exit("Not a zip file: " + path)
    n, cd_size, cd_off = struct.unpack_from("<HII", tail, k + 10)
    f.seek(cd_off)
    cd = f.read(cd_size)
    ents, p = [], 0
    for _ in range(n):
        if cd[p:p + 4] != b"PK\x01\x02":
            sys.exit("Broken central directory in " + path)
        flag, method = struct.unpack_from("<HH", cd, p + 8)
        nl, el, cl = struct.unpack_from("<HHH", cd, p + 28)
        lho = struct.unpack_from("<I", cd, p + 42)[0]
        rec = cd[p:p + 46 + nl + el + cl]
        ents.append({"name": rec[46:46 + nl].decode("utf-8", "replace"), "flag": flag,
                     "method": method, "lho": lho, "cd": bytearray(rec)})
        p += len(rec)
    byoff = sorted(ents, key=lambda e: e["lho"])
    for a, b in zip(byoff, byoff[1:] + [None]):
        a["end"] = b["lho"] if b else cd_off
    f.close()
    return ents


def write_disc(original, out, new_files):
    ents = zip_entries(original)
    names = {e["name"] for e in ents}
    for n in new_files:
        if n not in names:
            sys.exit("Entry not found in original disc: " + n)
    src = open(original, "rb")
    dst = open(out, "wb")
    for e in sorted(ents, key=lambda e: e["lho"]):
        e["new_lho"] = dst.tell()
        if e["name"] in new_files:
            data = new_files[e["name"]]
            crc = zlib.crc32(data) & 0xFFFFFFFF
            nm = e["name"].encode("utf-8")
            mt, md = struct.unpack_from("<HH", e["cd"], 12)
            dst.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 10, 0, 0, mt, md,
                                  crc, len(data), len(data), len(nm), 0) + nm)
            dst.write(data)
            cd = e["cd"]
            struct.pack_into("<HH", cd, 8, 0, 0)                    # flags, method: plain stored
            struct.pack_into("<III", cd, 16, crc, len(data), len(data))
        else:
            src.seek(e["lho"])
            left = e["end"] - e["lho"]
            while left:
                buf = src.read(min(left, 1 << 22))
                if not buf:
                    sys.exit("Unexpected end of original disc")
                dst.write(buf)
                left -= len(buf)
    cd_off = dst.tell()
    for e in ents:
        struct.pack_into("<I", e["cd"], 42, e["new_lho"])
        dst.write(e["cd"])
    cd_size = dst.tell() - cd_off
    dst.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(ents), len(ents), cd_size, cd_off, 0))
    dst.close()
    src.close()
    return len(ents)


def verify_disc(original, out, new_files):
    a = {e["name"]: e for e in zip_entries(original)}
    b = {e["name"]: e for e in zip_entries(out)}
    if a.keys() != b.keys():
        sys.exit("Verify failed: file list differs")
    fa, fb = open(original, "rb"), open(out, "rb")
    for name, eb in b.items():
        if name in new_files:
            fb.seek(eb["lho"])
            h = fb.read(30)
            nl, el = struct.unpack_from("<HH", h, 26)
            fb.seek(eb["lho"] + 30 + nl + el)
            if fb.read(len(new_files[name])) != new_files[name]:
                sys.exit("Verify failed: " + name)
        else:
            ea = a[name]
            if ea["end"] - ea["lho"] != eb["end"] - eb["lho"]:
                sys.exit("Verify failed (size): " + name)
            fa.seek(ea["lho"]); fb.seek(eb["lho"])
            left = ea["end"] - ea["lho"]
            while left:
                k = min(left, 1 << 22)
                if fa.read(k) != fb.read(k):
                    sys.exit("Verify failed (content): " + name)
                left -= k
    fa.close(); fb.close()


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--toolkit", required=True)
    ap.add_argument("--original", required=True, help="untouched game disc")
    ap.add_argument("--out", required=True, help="where to write the Thai disc")
    a = ap.parse_args()
    tk = os.path.abspath(a.toolkit)
    t0 = time.time()

    z7 = os.path.join(tk, "utils", "7zip", "x64", "7za.exe")
    key = os.path.join(tk, "utils", "d")
    qb = os.path.join(tk, "utils", "quickbms", "quickbms.exe")
    bms = os.path.join(tk, "utils", "quickbms", "sos-fomt_lzs.bms")
    for p in (z7, key, qb, bms, it.texconv(tk)):
        if not os.path.exists(p):
            sys.exit("Missing toolkit file: " + p)

    work = os.path.join(tk, "_thai_build")
    shutil.rmtree(work, ignore_errors=True)
    lz, dc, chk, base = (os.path.join(work, d) for d in ("lz", "dc", "chk", "root"))
    for d in (lz, dc, chk, base):
        os.makedirs(d)

    log("[1/6] Reading the 2 game files from the original disc ...")
    with open(key, "rb") as k:
        run([z7, "x", os.path.abspath(a.original)] + [t.replace("/", "\\") for t, _ in TARGETS]
            + ["-o" + lz, "-aoa", "-y", "-sccwin"], stdin=k)
    for t, _ in TARGETS:
        if not os.path.exists(os.path.join(lz, t)):
            sys.exit("Could not read " + t + " from " + a.original)

    log("[2/6] Decompressing ...")
    run([qb, "-Y", "-D", "-o", "-F", "{}.lzs", bms, lz, dc])
    arcs = {}
    for t, rel in TARGETS:
        p = os.path.join(dc, t + ".dcmp")
        if not os.path.exists(p):
            sys.exit("Decompress failed: " + p)
        data = open(p, "rb").read()
        ents = arc_read(data)
        folder = os.path.join(base, rel)
        os.makedirs(folder)
        for e in ents:
            open(os.path.join(folder, e["name"]), "wb").write(data[e["off"]:e["off"] + e["size"]])
        arcs[t] = (p, data, ents, folder)

    log("[3/6] Adding Thai text and fonts ...")
    it.precheck(tk, None, base)
    it.do_text(tk, base)
    it.do_fonts(tk, base)

    log("[4/6] Repacking ...")
    for t, (p, data, ents, folder) in arcs.items():
        files = {}
        for e in ents:
            f = it.find_case(folder, e["name"])
            files[e["name"]] = open(f, "rb").read()
        open(p, "wb").write(arc_write(data, ents, files))

    log("[5/6] Compressing (this is the slow part) ...")
    run([qb, "-D", "-o", "-w", "-r", "-r", "-r", bms, lz, dc])
    run([qb, "-Y", "-D", "-o", "-F", "{}.lzs", bms, lz, chk])
    new_files = {}
    for t, _ in TARGETS:
        want = open(os.path.join(dc, t + ".dcmp"), "rb").read()
        got = open(os.path.join(chk, t + ".dcmp"), "rb").read()
        if want != got:
            sys.exit("Compression check failed for " + t)
        new_files[t] = open(os.path.join(lz, t), "rb").read()

    log("[6/6] Writing the new disc ...")
    tmp = os.path.abspath(a.out) + ".tmp"
    n = write_disc(os.path.abspath(a.original), tmp, new_files)
    verify_disc(os.path.abspath(a.original), tmp, new_files)
    os.replace(tmp, os.path.abspath(a.out))
    shutil.rmtree(work, ignore_errors=True)
    log(f"Done: {n} files, 2 changed, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
