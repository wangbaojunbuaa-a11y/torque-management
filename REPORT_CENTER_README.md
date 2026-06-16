# IGBT 拧紧报表中心

这是独立于拧紧工作站的小程序，入口为 `report_center_main.py`。它只读取各产线共享出来的 `data/torque.db`，不会写入产线数据库。

## 工作流程

1. 按配置轮询各产线 `torque.db`。
2. 读取已完成第三次拧紧，且第二次、第三次 OK 数量都满足要求的水冷基板。
3. 按 CoatingRecordAndReport 的方式查询 MES：
   - `plan_part.serial_number`
   - `doc_key_part_info.product_born_code`
   - `doc_key_part_info.part_barcode`
   - `doc_key_part_info.part_code`
4. 如果 MES 零件条码中包含水冷基板条码，则绑定产品序列号。
5. 先生成 `{产品序列号}-拧紧记录表.xlsx` 到本地暂存目录。
6. 从文件名解析订单号，到归档根目录下查找包含该订单号的文件夹，找到后移动进去。
7. 报表中心用自己的 `data/report_center.db` 记录状态和去重，避免重复生成。

## 配置

首次运行会自动生成 `report_center_config.json`，也可以参考 `report_center_config.example.json`。

建议产线数据库路径使用 UNC 路径，例如：

```text
\\LineServer01\TorqueData\data\torque.db
```

不要优先使用 `Z:\data\torque.db` 这类映射盘符，因为不同服务器的盘符可能不同。

报表路径逻辑与 `CoatingRecordAndReport` 一致：

1. 本地暂存目录：默认 `reports/`。
2. 生成文件名：`产品序列号-拧紧记录表.xlsx`。
3. 订单号解析：取产品序列号中最后一个 `%` 后面的内容。
4. 归档：在归档根目录下查找名称包含订单号的文件夹，找到后移动报表。

## 报表格式

Excel 报表包含：

- 产品序列号、水冷基板条码、产品类型、产线、生成时间
- 序号、轮次、程序号、目标扭矩、拧紧扭矩、拧紧角度、拧紧时间、作业人员姓名、作业人员工号、结果
- MES 中筛选出的 IGBT 清单

单元格会自动设置列宽、换行、边框、冻结表头，并对扭矩/角度列使用三位小数格式。
