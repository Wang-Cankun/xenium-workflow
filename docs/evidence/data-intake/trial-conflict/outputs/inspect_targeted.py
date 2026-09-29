from pathlib import Path
import json
import h5py
import numpy as np

source=Path("received/expression.h5ad")
with h5py.File(source,"r") as f:
    def strings(key):
        return f[key].asstr()[()].tolist()
    ids=strings("obs/_index")
    specimens=strings("obs/specimen")
    cores=strings("obs/core")
    groups=strings("obs/group")
    coords=f["obsm/spatial"][()]
    rows=[dict(row=i, specimen=s, barcode=b, core=c, group=g, spatial=xy.tolist())
          for i,(s,b,c,g,xy) in enumerate(zip(specimens,ids,cores,groups,coords))]
    frames=[]
    for key in sorted(set(zip(specimens,cores))):
        sub=coords[[i for i,(s,c) in enumerate(zip(specimens,cores)) if (s,c)==key]]
        frames.append(dict(specimen=key[0],core=key[1],cells=len(sub),
            nonfinite=int((~np.isfinite(sub)).sum()),
            duplicate_coordinate_rows=len(sub)-len(np.unique(sub,axis=0)),
            axis_min=sub.min(axis=0).tolist(),axis_max=sub.max(axis=0).tolist(),
            collapsed_axes=(sub.min(axis=0)==sub.max(axis=0)).tolist()))
    result=dict(input=str(source),mode="h5py read-only; every dataset read in full",
        root_attribute_names=list(f.attrs),obs_columns=list(f["obs"]),
        feature_labels=strings("var/_index"),rows=rows,
        specimen_barcode_duplicate_rows=len(rows)-len(set(zip(specimens,ids))),
        matrices={key:f[key][()].tolist() for key in ["X","layers/scaled"]},
        coordinate_frames=frames,
        raw_group_present="raw" in f,
        layer_names=list(f["layers"]),
        biological_replicate_field_present=any(k in f["obs"] for k in ["replicate","biological_replicate","patient","donor","animal"]),
        cell_type_field_present=any(k in f["obs"] for k in ["cell_type","celltype","annotation"]))
Path("outputs/targeted-inspection.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
