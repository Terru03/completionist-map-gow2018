"""Build a chest/Raven coexistence candidate against the current completion baseline."""
from pathlib import Path
import json
import struct
import collectible_family_art as art

PACK_HASHES = {'.texpack': 'ba5522c090d7b3ee20f3edf41d488aadfbda40f3467b50ee02905303f084a200',
               '.texpack.toc': 'e3ff15f79b33ea4bb0461c665a323052befecc5b22e4a31feb4d837629ec7acc'}


def checked_pack(path, suffix):
    raw = path.read_bytes()
    art.need(art.sha(raw) == PACK_HASHES[suffix], 'historical texture pack differs: ' + suffix)
    return raw


def build():
    old = art.ROOT / "build/nornir-map-only-art-probe/candidate/game-root"
    raw = (old / art.WAD).read_bytes()
    art.need(art.sha(raw) == "539ca1823fe5deca64349772ec9f26d4e7b73af1e0a077b852dbb1dcec549caa",
             "historical artwork donor differs")
    records = art.logical.parse_wad(raw)
    textures = {}
    for role in ("diffuse", "emissive"):
        matches = [r for r in records if r["kind"] == 1 and r["data"] and
                   r["name"].startswith("TX_cm_nornir_chest_" + role[:4] + "_")]
        art.need(len(matches) == 1, "chest texture definition absent")
        definition = matches[0]
        name = definition["name"]
        _, gpu = art.clone.unique_texture(records, name, gpu=True)
        textures[role] = {"name": name, "file_hash": int(name.rsplit("_", 1)[1], 16),
                          "user_hash": struct.unpack_from("<Q", definition["data"], 0x9C)[0],
                          "resident": bytes(gpu["data"])}
    source = art.BUILD / "baseline"
    spec = art.spec_for("nornir_chest")
    resources = {"nornir_chest": spec["resource"]}
    outputs, proof = {}, {}
    outputs[art.WAD], proof[art.WAD] = art.build_wad((source / art.WAD).read_bytes(), [(spec, textures)])
    outputs[art.MASTER], proof[art.MASTER] = art.build_master((source / art.MASTER).read_bytes(), resources)
    outputs[art.POOL], proof[art.POOL] = art.build_pool((source / art.POOL).read_bytes(), resources)
    boot = json.loads((source / art.BOOT).read_bytes())
    pack = "completionist_v105_family_art_probe"
    boot["patch-texpacks"].append("../../patch/pc_le/" + pack)
    outputs[art.BOOT] = (json.dumps(boot, indent=2) + "\n").encode()
    for suffix in (".texpack", ".texpack.toc"):
        outputs["exec/patch/pc_le/" + pack + suffix] = checked_pack(
            old / ("exec/patch/pc_le/completionist_v105_nornir_chest" + suffix), suffix)
    return art.freeze_package(outputs, proof, art.BUILD / "probe")


if __name__ == "__main__":
    result = build()
    print("ART_PROBE_BUILT", result["package_id"])
    print(json.dumps(result["proof"][art.POOL]))
