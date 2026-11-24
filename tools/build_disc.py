#!/usr/bin/env python3
"""
Build a Thai game disc that differs from the original in exactly 2 files.

Old way (full-rebuild.bat): unpack every asset (~4 GB), recompress all 881
files, re-zip 1 GB. Slow, needs ~8 GB free, and every asset in the game
(animations, maps, ...) comes out different from the original.

This way:
  1. decrypt the original disc with the toolkit's 7za (no asset unpacking);
     the mod changes only 2 of its files:
       resource/message/ichigo_message_all_US.lzs   (game text)
       resource/ui/font_data.lzs                     (fonts)
  2. decompress them (quickbms, same script the toolkit uses)
  3. unpack the archives, add Thai text + fonts (install_thai.py)
  4. repack the archives (128-byte aligned, like the original)
  5. recompress them (quickbms) and check they decode back byte-for-byte
  6. write the new disc (all plain, like pack-disc makes): the other files
     are the decrypted originals, checked by CRC against the original disc;
     only the 2 files are new.

Usage:  py -3 build_disc.py --toolkit <toolkit folder> --original <disc> --out <new disc>
"""
import argparse, os, shutil, struct, subprocess, sys, time, zipfile

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


# ------------------------------------------------------------------ zip
# The game reads a disc whose files are all encrypted (original) or all plain
# (what the toolkit's pack-disc makes). Mixing the two does NOT work, so the
# new disc is all plain: every file is the decrypted original, except the 2
# patched ones. Entry order and timestamps follow the original.
def write_disc(original, files_dir, out, new_files):
    src = zipfile.ZipFile(original)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED, allowZip64=True) as dst:
        for info in sorted(src.infolist(), key=lambda i: i.header_offset):
            zi = zipfile.ZipInfo(info.filename, info.date_time)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = info.external_attr
            if info.is_dir():
                dst.writestr(zi, b"")
            elif info.filename in new_files:
                dst.writestr(zi, new_files[info.filename])
            else:
                path = os.path.join(files_dir, *info.filename.split("/"))
                with open(path, "rb") as f, dst.open(zi, "w", force_zip64=False) as w:
                    shutil.copyfileobj(f, w, 1 << 22)
    return len(src.infolist())


def verify_disc(original, out, new_files):
    """Every unchanged file must have the original's CRC (= byte-identical content)."""
    a = {i.filename: i for i in zipfile.ZipFile(original).infolist()}
    zb = zipfile.ZipFile(out)
    b = {i.filename: i for i in zb.infolist()}
    if a.keys() != b.keys():
        sys.exit("Verify failed: file list differs")
    for name, ib in b.items():
        if ib.flag_bits & 1 or ib.compress_type != zipfile.ZIP_STORED:
            sys.exit("Verify failed (not plain stored): " + name)
        if name in new_files:
            if zb.read(name) != new_files[name]:
                sys.exit("Verify failed: " + name)
        elif (ib.CRC, ib.file_size) != (a[name].CRC, a[name].file_size):
            sys.exit("Verify failed (differs from original): " + name)


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

    log("[1/6] Reading the original disc (about 1 GB) ...")
    allx = os.path.join(work, "all")
    with open(key, "rb") as k:
        run([z7, "x", os.path.abspath(a.original), "-o" + allx, "-aoa", "-y", "-sccwin"], stdin=k)
    for t, _ in TARGETS:
        src = os.path.join(allx, *t.split("/"))
        if not os.path.exists(src):
            sys.exit("Could not read " + t + " from " + a.original)
        os.makedirs(os.path.dirname(os.path.join(lz, t)), exist_ok=True)
        shutil.copyfile(src, os.path.join(lz, t))

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
    n = write_disc(os.path.abspath(a.original), allx, tmp, new_files)
    verify_disc(os.path.abspath(a.original), tmp, new_files)
    os.replace(tmp, os.path.abspath(a.out))
    shutil.rmtree(work, ignore_errors=True)
    log(f"Done: {n} files, 2 changed, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
