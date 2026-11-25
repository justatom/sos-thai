#!/usr/bin/env python3
"""
Build the Thai game disc from an ORIGINAL game disc.

The mod changes exactly 2 files inside the disc:
    resource/message/ichigo_message_all_US.lzs   (game text)
    resource/ui/font_data.lzs                     (fonts)
Every other file in the new disc is the original, checked by CRC.

Steps
  1. decrypt the original disc with the toolkit's 7za (into a temp folder)
  2. decompress the 2 files with the toolkit's QuickBMS script, unpack them
  3. add Thai text + fonts (thai_patch.py, fonts re-encoded with texconv)
  4. repack them (128-byte aligned like the original), recompress with
     QuickBMS and check they decompress back byte-for-byte
  5. write the new disc: a plain stored zip, original entry order
     (the game loads an all-encrypted or an all-plain disc, never a mix)
  6. verify it, then replace the output file

Usage:
  py -3 build_disc.py --toolkit <sos-fomt_disc-toolkit folder>
                      --original <original disc> --out <game folder>\\disc
"""
import argparse, os, shutil, struct, subprocess, sys, time, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thai_patch as tp  # noqa: E402

MSG = "resource/message/ichigo_message_all_US.lzs"
FONT = "resource/ui/font_data.lzs"
TARGETS = [MSG, FONT]
ALIGN = 128


def log(*a):
    print(*a, flush=True)


def run(cmd, stdin=None):
    r = subprocess.run(cmd, stdin=stdin, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        sys.exit("Command failed:\n" + " ".join(cmd) + "\n" + (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:])


def native(rel):
    return os.path.join(*rel.split("/"))


# ------------------------------------------------------------------ .lzs.dcmp archive
# u16 count (shares bytes with entry 0), then 64-byte entries:
#   u16, u16, u32 offset, u32 size, u32 id, char name[0x30]
def arc_read(data):
    ents = []
    for i in range(struct.unpack_from("<H", data, 0)[0]):
        o = i * 64
        off, size = struct.unpack_from("<II", data, o + 4)
        name = data[o + 16:o + 64].split(b"\0")[0].decode("ascii")
        ents.append({"i": i, "off": off, "size": size, "name": name})
    return ents


def arc_unpack(data, folder):
    os.makedirs(folder)
    ents = arc_read(data)
    for e in ents:
        with open(os.path.join(folder, e["name"]), "wb") as f:
            f.write(data[e["off"]:e["off"] + e["size"]])
    return ents


def arc_pack(orig, ents, folder):
    order = sorted(ents, key=lambda e: e["off"])
    out = bytearray(orig[:order[0]["off"]])
    for e in order:
        out += b"\0" * ((-len(out)) % ALIGN)
        body = open(tp.find_case(folder, e["name"]), "rb").read()
        struct.pack_into("<II", out, e["i"] * 64 + 4, len(out), len(body))
        out += body
    out += b"\0" * ((-len(out)) % ALIGN)
    return bytes(out)


# ------------------------------------------------------------------ disc (zip)
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
                with open(os.path.join(files_dir, native(info.filename)), "rb") as f, \
                        dst.open(zi, "w", force_zip64=False) as w:
                    shutil.copyfileobj(f, w, 1 << 22)
    return len(src.infolist())


def verify_disc(original, out, new_files):
    a = {i.filename: i for i in zipfile.ZipFile(original).infolist()}
    zb = zipfile.ZipFile(out)
    b = {i.filename: i for i in zb.infolist()}
    if a.keys() != b.keys():
        sys.exit("Verify failed: file list differs from the original")
    for name, ib in b.items():
        if ib.flag_bits & 1 or ib.compress_type != zipfile.ZIP_STORED:
            sys.exit("Verify failed (not plain): " + name)
        if name in new_files:
            if zb.read(name) != new_files[name]:
                sys.exit("Verify failed: " + name)
        elif (ib.CRC, ib.file_size) != (a[name].CRC, a[name].file_size):
            sys.exit("Verify failed (differs from original): " + name)


# ------------------------------------------------------------------ main
def find_tool(tk, *names):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in [os.path.join(here, "bin", names[-1]), os.path.join(tk, "utils", *names)]:
        if os.path.exists(p):
            return p
    sys.exit("Missing tool: " + names[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--toolkit", required=True, help="sos-fomt_disc-toolkit folder")
    ap.add_argument("--original", required=True, help="original (unmodded) game disc")
    ap.add_argument("--out", required=True, help="where to write the Thai disc")
    a = ap.parse_args()
    tk, original, out = (os.path.abspath(p) for p in (a.toolkit, a.original, a.out))
    t0 = time.time()

    z7 = os.path.join(tk, "utils", "7zip", "x64", "7za.exe")
    key = os.path.join(tk, "utils", "d")
    qb = os.path.join(tk, "utils", "quickbms", "quickbms.exe")
    bms = os.path.join(tk, "utils", "quickbms", "sos-fomt_lzs.bms")
    for p in (z7, key, qb, bms):
        if not os.path.exists(p):
            sys.exit("Missing toolkit file: " + p)
    texconv = find_tool(tk, "texconv.exe")
    if os.path.normcase(original) == os.path.normcase(out):
        sys.exit("--original and --out must be different files")

    work = os.path.join(os.path.dirname(out), "_thai_build")
    shutil.rmtree(work, ignore_errors=True)
    allx, lz, dc, chk, root = (os.path.join(work, d) for d in ("all", "lz", "dc", "chk", "root"))
    for d in (lz, dc, chk, root):
        os.makedirs(d)

    try:
        log("[1/6] Decrypting the original disc ...")
        with open(key, "rb") as k:
            run([z7, "x", original, "-o" + allx, "-aoa", "-y", "-sccwin"], stdin=k)
        for t in TARGETS:
            src = os.path.join(allx, native(t))
            if not os.path.exists(src):
                sys.exit("Could not read " + t + " from " + original)
            os.makedirs(os.path.dirname(os.path.join(lz, native(t))), exist_ok=True)
            shutil.copyfile(src, os.path.join(lz, native(t)))

        log("[2/6] Unpacking text and fonts ...")
        run([qb, "-Y", "-D", "-o", "-F", "{}.lzs", bms, lz, dc])
        arcs = {}
        for t in TARGETS:
            p = os.path.join(dc, native(t) + ".dcmp")
            if not os.path.exists(p):
                sys.exit("Decompress failed: " + t)
            data = open(p, "rb").read()
            folder = os.path.join(root, os.path.basename(t))
            arcs[t] = (p, data, arc_unpack(data, folder), folder)

        log("[3/6] Adding Thai text and fonts ...")
        tp.patch_text(arcs[MSG][3])
        tp.patch_fonts(arcs[FONT][3], texconv)

        log("[4/6] Repacking ...")
        for p, data, ents, folder in arcs.values():
            open(p, "wb").write(arc_pack(data, ents, folder))

        log("[5/6] Compressing and checking ...")
        run([qb, "-D", "-o", "-w", "-r", "-r", "-r", bms, lz, dc])
        run([qb, "-Y", "-D", "-o", "-F", "{}.lzs", bms, lz, chk])
        new_files = {}
        for t in TARGETS:
            if open(os.path.join(dc, native(t) + ".dcmp"), "rb").read() != \
                    open(os.path.join(chk, native(t) + ".dcmp"), "rb").read():
                sys.exit("Compression check failed: " + t)
            new_files[t] = open(os.path.join(lz, native(t)), "rb").read()

        log("[6/6] Writing the new disc ...")
        tmp = out + ".tmp"
        n = write_disc(original, allx, tmp, new_files)
        verify_disc(original, tmp, new_files)
        os.replace(tmp, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if os.path.exists(out + ".tmp"):
            os.remove(out + ".tmp")
    log(f"Done: {n} files, 2 changed, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
