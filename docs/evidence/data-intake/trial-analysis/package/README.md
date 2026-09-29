# Curated Xenium delivery

This delivery consists of a processed expression object, annotation and coordinate exports, this README and the sender checksum list. Native images, native count matrices and transcript outputs are outside this curated delivery.

`expression.h5ad`: X is log1p-normalized expression; layers/scaled contains centered standardized values. Raw counts were not exported. The obs index is the supplied cell barcode, unique only within each core. `core` defines the coordinate frame. `obsm/spatial` gives cell-centroid x/y in core-local micrometers and is aligned to obs rows. The object contains cores A and B; their local coordinate ranges may overlap. Group labels are descriptive; animal/tumor identities and biological independence are not provided.

`annotations.csv` and `coordinates.csv` are exports keyed by (core, cell_id); their row ordering is arbitrary. Use the supplied keys when checking correspondence. The coordinate export is intended to cover the object's cells. Annotations were supplied by the collaborator and have not been revalidated. The sender checksum list was supplied with the delivery; its relationship to this local copy has not been checked.
