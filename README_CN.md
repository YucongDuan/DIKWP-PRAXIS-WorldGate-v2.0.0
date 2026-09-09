# DIKWP-PRAXIS-OS 2.0.0 · WORLDGATE

创作者：段玉聪（Yucong Duan）。采用 Apache-2.0 许可证。


## 把评估结论变成执行当下的有限资格

新版保留 v1 全部源代码和原有评测命令，在其旁边增加真实本地库存操作内核。它不把“评测通过”“具备能力”“得到授权”“真实完成”和“可以补偿”混为一件事。

### 首次运行

```bash
python -m pip install -r requirements.txt
python dist/praxis_v2.pyz demo --out first-run
```

完整演示包含旧版 432 次执行、新版 23 个运行时故障场景、并发预算争用、两数据库交付实验、有限规则修复、序贯风险监测和独立签名撤销。所有数据及批准均为合成，未连接真实模型、支付或生产平台。

双击 `web/praxis_v2.html` 可查看中英文结果。该页面不是执行引擎，也不会存放私钥；它可导入新的 summary.json 并导出未签名的操作草稿。真实执行使用 Python 程序。

### 检查签名和重新构造结果

```bash
python dist/praxis_v2.pyz replay first-run/runtime/verified-and-compensated/world.json --anchor first-run/runtime/verified-and-compensated/anchor.json --trust first-run/runtime/verified-and-compensated/trust.json
```

生产试点应独立保存最新公钥信任根和签名锚。把根和数据放在同一个压缩包中，不能单独证明外部身份或阻止整包回退。

### 安全边界

新内核依赖 PyCA cryptography（本次测试 46.0.4），不是零第三方依赖。唯一可实际改变状态的适配器是本地 `inventory.reserve`。prepare 不扣减；commit 在同一事务中重新检查权限、证据、预算和版本，并同步保存副作用与回执；独立只读观察确认后才得到 VERIFIED_LOCAL_EFFECT。

补偿必须确认没有后续写入，发生冲突就停止。撤销证据使相关授权失效，不抹去已经发生的历史。不可信智能体不得直接持有数据库、审批密钥或主机管理员权限。本系统不提供操作系统沙箱、自然人认证、真实支付或生产上线保障。

### 文件导航

`docs/report_cn.docx`、`docs/report_en.docx`：完整双语报告。`docs/comparison.csv`：16 项逐项对照。`docs/PROTOCOL.md`：消息协议和 SDK。`docs/SECURITY_MODEL.md`：信任模型与剩余风险。`verification/`：实际核验。`legacy/`：旧版说明和测试。代码及原创文档采用 Apache-2.0。
