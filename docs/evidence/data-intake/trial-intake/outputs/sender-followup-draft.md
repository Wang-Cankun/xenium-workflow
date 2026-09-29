Subject: Please check missing Xenium count matrices and morphology paths for regionA/regionB

Hi,

We compared our downloaded copy against the supplied complete shared-folder inventory. Both region READMEs specify the native MEX triplet with no alternative matrix representation. Could you please check these paths relative to the delivery root?

1. `regionA/cell_feature_matrix/matrix.mtx.gz` is absent from both the shared-folder inventory and our copy. Please check the intended source export and provide this file, or clarify any change to the agreed count representation. The barcodes and features files are present, but they do not contain the count matrix.
2. `regionB/cell_feature_matrix/matrix.mtx.gz` is listed in the shared-folder inventory at 93 bytes but is absent from our copy. Please confirm that it is currently available and provide the exact download location or resend that file. We cannot determine from these inventories whether it was missed during download or changed afterward.
3. `regionA/experiment.xenium` references `regionA/morphology.ome.tif`, which is absent from both inventories. Please check that path in the intended source. If the reference is outdated, please provide the correct relative path and clarify which image should be used for morphology review. We received `regionA/aux_outputs/morphology_focus_qc_masks/morphology.ome.tif`, but cannot treat the QC-mask file as the referenced morphology original.
4. Please identify the intended morphology image path for regionB; no image is listed under regionB in the supplied inventory or our copy. Please also confirm whether any morphology files were intentionally excluded from either region.

Please provide a manifest of the complete intended two-region source delivery, including relative paths, file types, byte sizes, total regular-file count and total bytes, and any intentional exclusions. Please distinguish the intended source/export from the current shared folder, and let us know what you find in the original outputs for the paths above. The supplied inventory establishes the shared folder's listing, but does not establish that the shared folder contains all intended files.

For context, both inventories total 9 files and 781 bytes; our copy additionally contains `regionB/download-note.txt` at 93 bytes, so matching totals conceal the missing regionB matrix. Please confirm the purpose of that note. We have not verified file contents or the supplied checksum list.

Thank you.

---
Draft only — not sent.
