import json

data = json.load(open('config/collectibles/v0.10.5/all-collectibles.json', 'r', encoding='utf-8'))
arts = [x for x in data['collectibles'] if x.get('family') == 'artefact']
known = {'Alfheim', 'Brooch', 'Cup', 'Horn', 'Mask', 'Ship Head', 'Toy', 'Lambs Cress'}

type_for_art = {}
res_for_art = {}

for a in arts:
    cid = a['catalogue_id']
    attrs = a.get('native', {}).get('attribute_values', [])
    types = [x for x in attrs if x in known]
    res = [x for x in attrs if any(x.startswith(p) for p in ['Alfheim', 'Brooch', 'Ship', 'LostToy', 'NorseMask', 'Cup', 'Horn']) and x not in known]
    assert len(res) == 1, f"Expected 1 resource for {cid}, got {res}"
    type_for_art[cid] = types[0] if types else None
    res_for_art[cid] = res[0]

print(f"Total mapped: {len(res_for_art)}")
with open('tools/v0.10.5/artefact_resources.lua', 'w', encoding='utf-8') as f:
    f.write("local artefactResources = {\n")
    for cid, r in res_for_art.items():
        f.write(f'  ["{cid}"] = "{r}",\n')
    f.write("}\n")
print("Wrote tools/v0.10.5/artefact_resources.lua")
