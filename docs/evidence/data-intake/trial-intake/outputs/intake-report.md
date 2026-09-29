---
title: "两区域 Xenium 交付完整性核查"
type: data-intake
received: "received/（本地）"
baseline: "shared-folder-inventory.json；two-region-delivery"
---

下载副本未完整匹配共享目录基线；共享目录基线也未满足已声明的交付范围。两区均缺少承诺的 MEX 计数矩阵文件，regionA 另有形态学图像引用未得到满足。本次为元数据核查，未计算校验和，也未判定矩阵、图像内容或生物学质量。

## 范围与覆盖

[交付说明](../delivery-notes.md)要求 regionA、regionB 用于表达探索和形态学审阅；两区 README 均明确要求原生 MEX 三件套 `matrix.mtx.gz`、`barcodes.tsv.gz`、`features.tsv.gz`，没有声明替代矩阵格式。无约定排除项。

| 证据 | 观察区间（UTC，2026-09-18） | 覆盖 | 普通文件 / 总字节 |
|---|---|---|---|
| [提供的共享目录清单](../shared-folder-inventory.json) | 23:42:12.264978–23:42:12.293874 | 完整元数据枚举；无跳过、错误或排除 | 9 / 781 |
| [本地接收目录清单](evidence/received-inventory.json) | 23:45:27.601654–23:45:27.649405 | 完整元数据枚举；无跳过、错误或排除 | 9 / 781 |

两边均有 6 个目录，无符号链接或其他对象。两次观察不构成同时、原子的快照。共享目录源路径仅作为清单标识读取，未访问该目录或仪器原始输出。元数据清单不验证文件内容是否已完整下载；已读取的文本文件只证明所读文本可访问。

## 逐路径发现

所有路径均相对于交付根目录。[完整比较结果](evidence/inventory-differences.json)确认：缺少 1 个基线路径，接收侧多出 1 个路径；8 个共同文件路径、类型和大小相同；无类型或大小冲突。

| 路径 | 共享目录基线 | 下载副本 | 结论与影响 |
|---|---|---|---|
| `regionA/cell_feature_matrix/matrix.mtx.gz` | 缺失 | 缺失 | 不满足 regionA README 的 MEX 承诺；缺项在共享目录观察中已存在，不能仅归因于下载。无法判断原始输出是否存在该文件，或在何次整理、上传中遗漏。 |
| `regionB/cell_feature_matrix/matrix.mtx.gz` | 普通文件，93 字节 | 缺失 | 确认下载副本相对基线缺项；不能据此区分漏选、下载失败、源目录变化或本地后续删除。 |
| `regionA/morphology.ome.tif` | 缺失 | 缺失 | `regionA/experiment.xenium` 的 `morphology_filepath` 指向此路径；引用未满足。不能由引用推断原始文件曾经存在，需核实图像位置或陈旧引用。 |
| `regionA/aux_outputs/morphology_focus_qc_masks/morphology.ome.tif` | 普通文件，44 字节 | 同路径、同大小 | QC masks 路径下的同名文件不能视为形态学原图替代品；未解析图像内容。 |
| `regionB/download-note.txt` | 缺失 | 普通文件，93 字节 | 接收侧独有，不能认定为不应交付；它与缺失矩阵同为 93 字节，解释了两边文件总数和总字节相同，但不消除缺项。 |

两区的条码和特征标签文件都在，但标签不是计数；当前副本没有完整的已承诺 MEX 计数表示，表达探索所需的计数输入尚未交齐。清单中也没有声明的替代矩阵文件。regionB 未观察到形态学图像；交付说明要求形态学审阅，但尚未给出其确切图像路径，需发件方明确。这是交付信息缺口，不能擅自规定某一原生文件名必须存在。

## 未解决项与下一步

请发件方核对两区完整预期源交付、补齐矩阵、解释 regionA 图像引用，并给出两区形态学图像的准确相对路径。共享目录枚举完整不证明其覆盖全部预期或原始仪器输出。比较相同的元数据也不证明字节相同；[发件方校验和列表](../sender-checksums.txt)只覆盖 regionB 矩阵一个路径，算法未声明，本次按要求没有执行本地哈希校验。没有解压、解析矩阵或图像，也没有下载、修复或发送消息。

已保存[未发送的英文核对草稿](sender-followup-draft.md)。必要的文字依据与路径观察见[范围证据](evidence/scope-evidence.json)；实际命令、退出码、标准输出和错误输出见[执行记录](evidence/command-results.json)，汇总见[运行结果](evidence/run-summary.json)。

复现时在本工作目录执行（输出目录必须尚不存在）：

```sh
python outputs/reproduce.py outputs/recheck
```

[复现脚本](reproduce.py)只读取指定输入和本地元数据，使用随技能提供的清单工具，结果写入新的 `outputs/` 子目录。
