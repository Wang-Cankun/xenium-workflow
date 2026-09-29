---
title: "四份 Xenium 交付：接收与分析输入检查"
type: data-check
package: "<workspace>/trial-scope/deliveries"
baseline: "delivery-agreements.md；无来源目录或发送方清单"
---

`explicit`、`unclear` 和 `additional` 各提供可检查的 S1/S2 处理后表达矩阵及局部坐标；`empty-candidate` 仅提供元数据、特征标签和坐标，没有表达矩阵。以下按交付约定分别判断，不选择下游方法，也不将接收差异等同于全部分析输入不可用。

## 逐份结论

约定依据为 [delivery-agreements.md](../delivery-agreements.md)。表中缺失结论来自各接收目录的完整枚举及对象级检查，不能说明文件在来源端是否曾经存在或遗漏发生在哪一步。

| 交付 | 约定与接收结论 | 当前可用内容与后续动作 | 检查证据 |
|---|---|---|---|
| `explicit` | 约定的 `expression.h5ad`、`README.md` 均存在；H5AD 确实含 S1、S2，满足本次明确的文件与标本范围。原生图像及其他原生输出不在约定内，无须作为缺件追索。 | 可继续查看 S1/S2 的处理后表达和分别绘制局部坐标。无需补齐约定外原生文件。 | [清单](explicit.inventory.json)、[完整检查](explicit.full.json) |
| `unclear` | 观察到 `expression.h5ad`、`README.md`；没有已确认的完整交付范围或来源清单，因此不能判定交付完整或认定其他文件缺失。README 仅解释对象语义。 | S1/S2 的表达和坐标可用；发送方与接收方需确认承诺的文件、表示形式、标本及有意排除项，再判断接收完整性。 | [清单](unclear.inventory.json)、[完整检查](unclear.full.json) |
| `additional` | H5AD 和 README 存在，但 H5AD 仅含 S1/S2，各 2 个细胞，缺少约定的 S3。确认未收到 `cell_feature_matrix/matrix.mtx.gz`、`cell_feature_matrix/barcodes.tsv.gz`、`cell_feature_matrix/features.tsv.gz`。 | S1/S2 的 H5AD 仍可用；它不是约定 MEX 的替代品。发送方需补交三条精确路径和包含 S3 的约定交付，或与接收方明确修订约定。来源不可访问，遗漏原因未定。 | [清单](additional.inventory.json)、[完整检查](additional.full.json) |
| `empty-candidate` | README 和候选 H5AD 可读取，但候选文件没有 `X`、表达层或 `raw/X`。存在 4 个细胞与 2 个特征的标签，不能代替表达值，因此没有满足“任一可读取、细胞／特征对应的表达矩阵”约定。 | 元数据和局部坐标可保留用于查看；不能据此做表达分析。发送方需提供任何约定允许的真实表达矩阵及其细胞／特征对应，无须指定必须为 MEX。 | [清单](empty-candidate.inventory.json)、[完整检查](empty-candidate.full.json) |

## 分析内容与对应关系

以下均对每份文件分别读取；三份有矩阵的交付观察结果一致，并未凭文件大小推断内容相同。见 [定向检查与原始数值](targeted-checks.json)及[检查脚本](targeted_checks.py)。

- **表达与特征：** `explicit`、`unclear`、`additional` 的 `X` 和 `layers/scaled` 均为 4×2 稠密矩阵，与 `obs`/`var` 轴长度相符；所有值已扫描，无非有限值、全零行或全零列。`X` 范围 0–0.9；各自 README 将其定义为 log1p 归一化表达。`scaled` 范围 −1.5–1.5，4 个负值符合其文档所述的中心化标准化语义，不是原始计数违规。未提供原始计数或 `raw/X`；不能将这些矩阵当作原始计数。`empty-candidate` 无矩阵可扫描，检查器返回无错误并不满足表达交付约定。
- **细胞身份：** 四份文件均为 S1、S2 各 2 个细胞；`_index` 中 `c1`、`c2` 跨标本重复，按 README 指定的 `(specimen, _index)` 复合键则全部唯一，无空值。不能仅用条形码跨标本连接。`obs` 各列长度一致；有矩阵时表达、元数据和 `obsm/spatial` 的内部细胞轴均为 4，无额外外部细胞表需要连接。此检查验证内部表示和维度，未独立验证发送方导出前的行来源。
- **坐标与边界：** 四份文件均有 4×2 有限坐标。S1→core A→control，S2→core B→case，无缺失或矛盾映射。每个 `(specimen, core)` 内坐标范围均为 x 0–1、y 0–2，无重复坐标或塌缩轴。跨两个局部坐标系出现相同坐标不构成重复细胞证据。README 声明单位为微米、坐标为 core 局部坐标；这是发送方语义声明，未通过图像独立校准。后续空间图或邻接图须分别处理标本／core。
- **生物学与处理背景：** 特征标签为 `G1`、`G2`，唯一且非空；物种、组织、基因标识符体系、原始面板、归一化参数、过滤历史和细胞类型注释未提供。group 标签可描述，但未给出生物学重复或标本间关系，不能据此建立独立生物学重复的组间比较。下游方法选定后，再由发送方补充实际相关的语义与重复映射；原生检测和分割质量未在本次检查。

## 覆盖与复现

每个 `deliveries/<交付>` 均完整枚举到 2 个普通文件：`README.md` 381 字节、`expression.h5ad` 19,712 字节，共 20,093 字节；无子目录、符号链接、排除项、跳过项或读取错误。每份清单保留各自扫描起止区间。枚举不是原子快照，不能排除未被观察到的并发变化。清单工具仅记录元数据可用性未知；本次另外成功读取了所有 README 和所报告的 H5 内容，确认这些内容实际可读。

文件对应以交付目录、相对路径和现场读取为依据；未提供可复用的发送方检查结果、文件版本标识或来源清单，因此未执行虚构的来源比较。没有计算校验和，未验证来源与接收文件的字节身份，也不能认证来源原始输出完整性。

按保存的本地配置使用 `python`：Python 3.14.7、NumPy 2.5.3、h5py 3.16.0。先做默认元数据检查，再对全部小矩阵执行完整数值扫描，并补充复合细胞键、逐 core 坐标和矩阵存在性检查。[实际命令、标准输出与退出码](commands.log)已保存；各 `*.metadata.json` 保留初检结果。未请求 AnnData 兼容性检查，因此未运行；h5py 可读不等于已验证 AnnData 读取。输入保持只读，未安装软件、传输数据、联系外部服务或发送邮件。
