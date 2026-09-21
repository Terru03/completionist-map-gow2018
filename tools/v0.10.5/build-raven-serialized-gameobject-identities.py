#!/usr/bin/env python3
"""Generate deterministic serialized GameObject identities for all 53 Ravens.

Static/read-only. Uses only shipped native catalogue data and the proven Raven
GameObject identity algorithm.

Proven structure:
  scene elements = reversed transform_chain record IDs with byte 12 decremented
  prototype/object element =
    perch/hop family: 805b030bf339564cb157837c52906465
    hover family:     50dafefd65605b41a2aed011a5f4ce22

The 64-bit object hash is the native 0x401 rolling hash over the concatenated
16-byte identity elements.

The serialized registry hash is WAD-specific. Packed Channel-A checkpoint
evidence proves it is the native case-folded 0x401 name hash of the WAD stem
without ".wad" (for example xpl200_funeral -> 0x4EC230253427B2B0).
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

MASK64=0xFFFFFFFFFFFFFFFF
PERCH_HOP_ELEMENT=bytes.fromhex("805b030bf339564cb157837c52906465")
HOVER_ELEMENT=bytes.fromhex("50dafefd65605b41a2aed011a5f4ce22")

KNOWN_ID="raven_642d0d164af0a5d4076e77933c549a5d"
KNOWN_OBJECT_HASH=0x98BE1707BA2D65A9
KNOWN_PAYLOAD_HEX="01b0b227342530c24ea9652dba0717be98"

PERCH_HOP_PROTOTYPES={
    "408280c2887ca5d7cba94feea56888d0",
    "f4f22e4546b2194891ad7f9a7c5b6dc4",
}
HOVER_PROTOTYPES={
    "0c397df6a1dcb23d8859241c3c713ac1",
    "3a519f6b5782fea73e617a71a7c726ce",
    "bd01be1157e065d6910e0c26c6fae6ab",
    "cbd08dc1fea41249375bb6b2fa795111",
}

def adjusted_record_id(hex_id:str)->bytes:
    raw=bytearray.fromhex(hex_id)
    if len(raw)!=16:raise ValueError(f"not a 16-byte record id: {hex_id}")
    raw[12]=(raw[12]-1)&0xFF
    return bytes(raw)

def scene_elements(row:dict)->tuple[list[bytes],list[dict]]:
    chain=row["source"]["transform_chain"]
    parent_proto=row["native"]["parent_prototype_id"]
    kept=[]
    skipped=[]
    for original_index,item in reversed(list(enumerate(chain))):
        element=adjusted_record_id(item["record_id"])
        # Proven against all 11 live-mismatching nested Ravens: when the
        # immediate parent's adjusted transform ID equals the child's
        # parent_prototype_id, that parent is a self-prototype container and
        # contributes no native GameObject identity element.
        if original_index==1 and element.hex()==parent_proto:
            skipped.append({
                "source_record_name":item["name"],
                "source_record_id":item["record_id"],
                "adjusted_identity_hex":element.hex(),
                "reason":"immediate_parent_adjusted_id_equals_parent_prototype_id",
            })
            continue
        kept.append(element)
    return kept,skipped

def prototype_element(row:dict)->bytes:
    pid=row["native"]["prototype_id"]
    if pid in PERCH_HOP_PROTOTYPES:return PERCH_HOP_ELEMENT
    if pid in HOVER_PROTOTYPES:return HOVER_ELEMENT
    raise ValueError(f"unclassified Raven prototype {pid}")

def identity_hash(elements:list[bytes])->int:
    value=0
    for element in elements:
        if len(element)!=16:raise ValueError("identity element length changed")
        for byte in element:
            value=((value+byte)*0x401)&MASK64
            value^=value>>6
    return value

def name_hash(name:str)->int:
    value=0
    for byte in name.upper().encode("ascii"):
        value=((value+byte)*0x401)&MASK64
        value^=value>>6
    return value

def registry_hash_for_wad(wad:str)->int:
    name=Path(wad).stem.lower()
    return name_hash(name)

def payload(registry_hash:int,object_hash:int)->bytes:
    return bytes([1])+registry_hash.to_bytes(8,"little")+object_hash.to_bytes(8,"little")

def build_row(row:dict)->dict:
    scene,skipped=scene_elements(row)
    proto=prototype_element(row)
    elements=scene+[proto]
    obj_hash=identity_hash(elements)
    registry_hash=registry_hash_for_wad(row["source"]["wad"])
    return {
        "catalogue_id":row["catalogue_id"],
        "display_name":row["display_name"],
        "wad":row["source"]["wad"],
        "instance_guid":row["native"]["instance_guid"],
        "prototype_id":row["native"]["prototype_id"],
        "identity_family":"perch_hop" if proto==PERCH_HOP_ELEMENT else "hover",
        "scene_identity_elements_hex":[x.hex() for x in scene],
        "skipped_self_prototype_parents":skipped,
        "prototype_identity_element_hex":proto.hex(),
        "identity_elements_hex":[x.hex() for x in elements],
        "registry_hash_hex":f"0x{registry_hash:016X}",
        "object_hash_hex":f"0x{obj_hash:016X}",
        "serialized_flag1_hex":payload(registry_hash,obj_hash).hex(),
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--catalogue",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--text",type=Path,required=True)
    a=ap.parse_args()

    cat=json.loads(a.catalogue.read_text(encoding="utf-8"))
    ravens=cat["ravens"]
    if len(ravens)!=53:raise RuntimeError(f"expected 53 Ravens, found {len(ravens)}")
    rows=[build_row(r) for r in ravens]
    ids=[r["catalogue_id"] for r in rows]
    hashes=[r["object_hash_hex"] for r in rows]
    payloads=[r["serialized_flag1_hex"] for r in rows]
    if len(ids)!=len(set(ids)):raise RuntimeError("duplicate catalogue IDs")
    if len(hashes)!=len(set(hashes)):raise RuntimeError("duplicate Raven object hashes")
    if len(payloads)!=len(set(payloads)):raise RuntimeError("duplicate Raven serialized identities")

    known=next(r for r in rows if r["catalogue_id"]==KNOWN_ID)
    if int(known["object_hash_hex"],16)!=KNOWN_OBJECT_HASH:
        raise RuntimeError(f"known Raven hash mismatch: {known['object_hash_hex']}")
    if known["serialized_flag1_hex"]!=KNOWN_PAYLOAD_HEX:
        raise RuntimeError(f"known Raven payload mismatch: {known['serialized_flag1_hex']}")

    result={
        "schema":1,
        "kind":"completionist_map_raven_serialized_gameobject_identity_catalogue",
        "registry_hash_mode":"native_name_hash_of_lowercase_wad_stem",
        "self_prototype_parent_rule":"omit immediate parent when adjusted transform record id equals native.parent_prototype_id",
        "count":len(rows),
        "unique_object_hashes":len(set(hashes)),
        "prototype_families":{
            "perch_hop":{
                "prototype_ids":sorted(PERCH_HOP_PROTOTYPES),
                "prototype_identity_element_hex":PERCH_HOP_ELEMENT.hex(),
            },
            "hover":{
                "prototype_ids":sorted(HOVER_PROTOTYPES),
                "prototype_identity_element_hex":HOVER_ELEMENT.hex(),
            },
        },
        "known_raven_validation":{
            "catalogue_id":KNOWN_ID,
            "expected_object_hash_hex":f"0x{KNOWN_OBJECT_HASH:016X}",
            "actual_object_hash_hex":known["object_hash_hex"],
            "expected_serialized_flag1_hex":KNOWN_PAYLOAD_HEX,
            "actual_serialized_flag1_hex":known["serialized_flag1_hex"],
            "exact_match":True,
        },
        "ravens":rows,
        "safety":{
            "static_only":True,
            "game_process_accessed":False,
            "save_opened":False,
            "save_or_progression_written":False,
        },
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    lines=[
        "Completionist Map - Raven serialized GameObject identities",
        f"count={len(rows)} unique_object_hashes={len(set(hashes))}",
        "registry_hash_mode=native_name_hash_of_lowercase_wad_stem",
        f"known_raven={KNOWN_ID} registry_hash={known['registry_hash_hex']} object_hash={known['object_hash_hex']} exact_match=true",
        "",
    ]
    for r in rows:
        lines.append(
            f"{r['catalogue_id']} family={r['identity_family']} "
            f"object_hash={r['object_hash_hex']} payload={r['serialized_flag1_hex']} "
            f"wad={r['wad']}"
        )
    a.text.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(
        "RAVEN_SERIALIZED_GAMEOBJECT_IDENTITIES_COMPLETE "
        f"count={len(rows)} unique={len(set(hashes))} known_exact=true"
    )

if __name__=="__main__":main()
