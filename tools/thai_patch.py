#!/usr/bin/env python3
"""
Thai text + font patching for SoS: Friends of Mineral Town (used by build_disc.py).

  patch_text(msg_dir)              msg_*.bin files of ichigo_message_all_US
      replaces the English text with translation/th.json and pre-positions
      tone marks (raised tone glyphs over upper vowels).
  patch_fonts(font_dir, texconv)   *_0.DDS + *_param.bin of font_data
      decodes each atlas, adds Thai glyphs (Noto Sans Thai SemiBold, SIL OFL)
      sized to the font's line height, updates the glyph table, re-encodes BC7.

Both refuse files that already contain Thai (never patch twice).
Needs Python 3.8+ and Pillow.
"""
import glob, json, os, shutil, struct, subprocess, sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is missing. Install it with:  py -3 -m pip install pillow")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = ["DFT_R9", "DFT_R8", "DFGBFY7", "DFGB_Y9", "FOT-SeuratCapiePro-EB",
         "FOT-UDMarugo_LargePro-B", "HOBBYWIR", "K2", "K3", "SHORHB__"]
RS = 0x20000          # param.bin: u16 cmap[0x10000] then 12-byte glyph records
REC = struct.Struct("<HHHBBbBH")   # codepoint, x, y, w, h, xoff, yoff, advance*16
THAI_SPAN_EM40 = 52    # typical Thai cluster height (raised tone top .. lower vowel bottom) at EM 40
ABOVE = {0x0E31, 0x0E34, 0x0E35, 0x0E36, 0x0E37, 0x0E47, 0x0E4D}
TONES = {0x0E48, 0x0E49, 0x0E4A, 0x0E4B, 0x0E4C}


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- message .bin
def read_bin(path):
    d = open(path, "rb").read()
    n = struct.unpack_from("<I", d, 0)[0] // 4
    out = []
    for i in range(n):
        off = struct.unpack_from("<I", d, i * 4)[0]
        j = off
        while d[j:j + 2] != b"\x00\x00":
            j += 2
        out.append(d[off:j].decode("utf-16-le"))
    return out


def write_bin(path, strs):
    buf = bytearray(len(strs) * 4)
    for i, s in enumerate(strs):
        struct.pack_into("<I", buf, i * 4, len(buf))
        buf += s.encode("utf-16-le") + b"\x00\x00"
    open(path, "wb").write(buf)


def shape(s):
    """Tone mark after an upper vowel -> raised tone glyph (private-use U+E048..E04C)."""
    out, prev = [], 0
    for ch in s:
        c = ord(ch)
        out.append(chr(0xE000 + c - 0x0E00) if c in TONES and prev in ABOVE else ch)
        prev = c
    return "".join(out)


def has_thai(s):
    return any(0x0E00 <= ord(c) <= 0x0E7F or 0xE000 <= ord(c) <= 0xE0FF for c in s)


def patch_text(msg_dir):
    tr = json.load(open(os.path.join(REPO, "translation", "th.json"), encoding="utf-8"))
    sysbin = os.path.join(msg_dir, "msg_System.bin")
    if not os.path.exists(sysbin):
        sys.exit("Cannot find " + sysbin)
    if any(has_thai(s) for s in read_bin(sysbin)):
        sys.exit("The game text already contains Thai: the disc used is not the original.")
    total = 0
    for fn, entries in tr.items():
        p = os.path.join(msg_dir, fn)
        if not os.path.exists(p):
            log("  ! missing", fn, "(skipped)")
            continue
        strs = read_bin(p)
        for idx, th in entries.items():
            i = int(idx)
            if i < len(strs):
                strs[i] = th
                total += 1
        write_bin(p, [shape(s) for s in strs])
    log(f"  text: {total} strings")


# ---------------------------------------------------------------- fonts
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Command failed:\n" + " ".join(cmd) + "\n" + r.stdout[-2000:] + r.stderr[-2000:])


def find_case(folder, name):
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    return None


def available_kits():
    ks = []
    for d in glob.glob(os.path.join(REPO, "fontkit", "em*")):
        try:
            ks.append(int(os.path.basename(d)[2:]))
        except ValueError:
            pass
    return sorted(ks)


def inject(name, atlas, param, kits):
    p = bytearray(open(param, "rb").read())
    n = (len(p) - RS) // 12

    def rec(i):
        return REC.unpack_from(p, RS + i * 12)

    def cmap(cp):
        return struct.unpack_from("<H", p, cp * 2)[0]

    if any(cmap(cp) != 0xFFFF for cp in range(0x0E01, 0x0E2F)):
        raise SystemExit(f"Font {name} already has Thai glyphs. Extract again from the ORIGINAL disc.")
    for cp in list(range(0x0E00, 0x0E80)) + list(range(0xE000, 0xE100)):
        struct.pack_into("<H", p, cp * 2, 0xFFFF)

    # Latin vertical band of this font = the space a line of text may safely occupy
    tops, bots = [], []
    for c in list(range(65, 91)) + list(range(97, 123)):
        i = cmap(c)
        if i != 0xFFFF and i < n:
            r = rec(i)
            tops.append(r[6]); bots.append(r[6] + r[4])
    lat_top, lat_bot = min(tops), max(bots)
    a = rec(cmap(0x41))
    baseline = a[6] + a[4]
    want = int(40 * (lat_bot - lat_top) / THAI_SPAN_EM40)
    em = max([k for k in kits if k <= want] or [kits[0]])

    kdir = os.path.join(REPO, "fontkit", f"em{em}")
    kit = json.load(open(os.path.join(kdir, "thai_metrics.json"), encoding="utf-8"))
    katlas = Image.open(os.path.join(kdir, "thai_atlas.png")).convert("RGBA")
    glyphs = kit["glyphs"]
    cons = sorted(g["xadv"] for g in glyphs
                  if g["cls"] == "full" and 0x0E01 <= g["cp"][0] <= 0x0E2E and g["xadv"] > 0)
    cons_adv = cons[len(cons) // 2]
    core = [g for g in glyphs if g["variant"] != "low"]
    t_top = min(g["yoff"] for g in core)
    t_bot = max(g["yoff"] + g["h"] for g in core)
    shift = baseline
    if shift + t_bot > lat_bot:
        shift = lat_bot - t_bot
    if shift + t_top < lat_top:
        shift = lat_top - t_top

    img = Image.open(atlas).convert("RGBA")
    W, H = img.size
    ink = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getprojection()[1]
    best, start = (0, 0), None
    for y in range(H + 1):
        free = y < H and not ink[y]
        if free and start is None:
            start = y
        if not free and start is not None:
            if y - start > best[1] - best[0]:
                best = (start, y)
            start = None
    y0, ymax = best[0] + 2, best[1] - 1

    pos, cx, cy, sh = {}, 2, y0, 0
    for g in sorted(glyphs, key=lambda g: -g["h"]):
        w, h = g["w"] + 2, g["h"] + 2
        if cx + w > W:
            cy += sh; cx = 2; sh = 0
        if sh == 0:
            sh = h
        pos[id(g)] = (cx, cy)
        cx += w
    if cy + sh > ymax:
        raise SystemExit(f"Not enough free space in the {name} atlas.")

    new, upd = [], {}
    for g in glyphs:
        gx, gy = pos[id(g)]
        img.alpha_composite(katlas.crop((g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"])), (gx, gy))
        cp = g["cp"][0]
        yoff = max(0, min(255, shift + g["yoff"]))
        if g["cls"] == "full":
            xoff, adv = g["xoff"], g["xadv"] * 16
        else:
            xoff, adv = max(-128, min(127, g["xoff"] - cons_adv + round(3 * em / 40))), 0
        idx = n + len(new)
        new.append(REC.pack(cp, gx, gy, g["w"], g["h"], xoff, yoff, adv))
        if g["cls"] == "tone":
            if g["variant"] == "normal":
                upd[cp] = idx
            elif g["variant"] == "raised":
                upd[0xE000 + cp - 0x0E00] = idx
        elif g["variant"] in ("base", "normal"):
            upd[cp] = idx
    p = p[:RS + n * 12]
    for r in new:
        p += r
    for cp, i in upd.items():
        struct.pack_into("<H", p, cp * 2, i)
    open(param, "wb").write(p)
    img.save(atlas)
    return em


def patch_fonts(font_dir, exe):
    p = find_case(font_dir, "FOT-UDMarugo_LargePro-B_param.bin")
    if not p:
        sys.exit("Cannot find the font files in " + font_dir)
    if struct.unpack_from("<H", open(p, "rb").read(), 0x0E01 * 2)[0] != 0xFFFF:
        sys.exit("The game fonts already contain Thai: the disc used is not the original.")
    work = os.path.join(font_dir, "_png")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    kits = available_kits()
    for name in FONTS:
        dds = find_case(font_dir, f"{name}_0.DDS")
        param = find_case(font_dir, f"{name}_param.bin")
        if not dds or not param:
            sys.exit("Font not found: " + name)
        run([exe, "-nologo", "-ft", "PNG", "-y", "-o", work, dds])
        png = find_case(work, f"{name}_0.png")
        em = inject(name, png, param, kits)
        log(f"  font {name}: Thai size {em}, encoding BC7 ...")
        run([exe, "-nologo", "-f", "BC7_UNORM", "-dx10", "-m", "1", "-y", "-o", font_dir, png])
    shutil.rmtree(work, ignore_errors=True)
