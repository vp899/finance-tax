# 财务报税系统

面向小规模纳税人的财务核算 + 报税辅助系统。
技术栈：**FastAPI + SQLite（后端） · Next.js + React + Tailwind CSS（前端）**。

## 功能总览

| 模块 | 功能 |
|---|---|
| 凭证管理 | 新增凭证（**智能补全**：科目编码/名称/拼音首字母、摘要历史）、查看/编辑/复制/作废、凭证汇总表 |
| 账簿 | 总账、明细账、余额表、序时账、多栏账（按明细科目分栏） |
| 财务报表 | 资产负债表、利润表、利润表季报、现金流量表、现金流量表季报 |
| 结转与反结转 | 结转销售成本、计提工资、计提折旧、摊销无形资产、结转本期损益、计提税金、计提所得税、免交增值税；一键反结转（作废对应凭证，报表自动回退） |
| 结账 | 结账检查（试算平衡 → 无草稿凭证 → 本期损益结平）、反结账、强制结账 |
| 财税设置 | 小规模纳税人 / 2013 小企业会计准则、凭证类型、科目期初（带试算平衡校验）、计量单位、币种、科目现金流量对照表、固定资产/无形资产 |
| 数据管理 | 所有账簿/报表导出 Excel、Excel 凭证导入（带模板）、SQLite 单文件备份与恢复 |

## 快速启动

```bash
# 1. 后端（端口 8000）
cd backend
pip3 install -r requirements.txt
bash restart.sh          # 或 bash run.sh

# 2. 前端（端口 3000）
cd ../frontend
npm install
npm run dev              # 生产环境用 npm run build && npm run start
```

浏览器打开 <http://localhost:3000>。后端 API 文档：<http://localhost:8000/docs>。

跨主机部署时设置前端环境变量指向后端地址：

```bash
NEXT_PUBLIC_API_URL=http://your-host:8000 npm run build
```

## 正确性保证

- 凭证校验：借贷必须平衡、必须使用末级科目、金额两位小数、结账期间锁定
- 试算平衡：期初 + 发生额全程保持 借方合计 = 贷方合计
- 报表勾稽恒等式：
  - 资产负债表 **资产 = 负债 + 所有者权益**（未分配利润自动并入未结转的本年损益，任何结转状态下都平衡）
  - 现金流量表 **期末现金 = 账面现金余额**
  - 利润表自动剔除结转损益凭证，结转后仍显示真实经营成果
- 跨年安全：期初余额按年度存放，报表/账簿计算严格限定在同一年度内

### 测试体系（共 334 项，全绿）

| 测试套件 | 用例数 | 覆盖 |
|---|---|---|
| `backend/tests/test_00_accounts.py` | 23 | 科目 CRUD/智能补全/期初试算平衡与非法录入 |
| `backend/tests/test_01_vouchers.py` | 33 | 凭证校验（不平衡/负数/非末级/两位小数等）、编号、查询、作废复制、现金流量自动对照 |
| `backend/tests/test_02_books_reports.py` | 36 | 五种账簿精确金额、报表精确金额、月报/季报/累计口径、三大报表勾稽恒等式 |
| `backend/tests/test_03_carryover.py` | 39 | 8 类结转精确金额、反结转回退、免征判定、结账/反结账/强制结账、锁期 |
| `backend/tests/test_04_settings_data.py` | 52 | 财税设置 CRUD、Excel 导出内容比对、导入成功/失败路径、备份/恢复/非法文件 |
| `backend/tests/e2e_test.py` | 83 断言 | 端到端完整业务流（建账→凭证→结转→报表→结账→导入导出→备份） |
| `frontend/__tests__/api.test.js` | 20 | 金额格式化、期间计算、API 请求/错误处理/上传 |
| `frontend/__tests__/ui.test.js` | 17 | Modal/Tabs/Money/Badge/Alert 等基础组件 |
| `frontend/__tests__/VoucherEditor.test.js` | 20 | 智能补全（拼音/键盘选择）、借贷平衡提示、保存载荷、错误展示 |
| `frontend/__tests__/pages.test.js` | 11 | 仪表盘/结转页交互与状态 |

```bash
# 后端（pytest 183 + e2e 83）
cd backend && python3 -m pytest tests/ -q && python3 tests/e2e_test.py

# 前端（jest 68）
cd frontend && npm test
```

## 目录结构

```
finance-tax-system/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── database.py       # SQLite 连接
│   │   ├── models.py         # 数据模型
│   │   ├── seed.py           # 默认科目表/现金流量项目/设置
│   │   ├── services/
│   │   │   ├── ledger.py     # 账簿与报表核心计算
│   │   │   ├── vouchers.py   # 凭证校验/编号/现金流量自动对照
│   │   │   ├── carryover.py  # 8 类结转 + 结账
│   │   │   └── excel_io.py   # Excel 导入导出
│   │   └── routers/          # accounts/vouchers/books/reports/carryover/settings/data_io
│   ├── data/finance.db       # SQLite 数据文件（备份即拷贝此文件或用备份接口）
│   └── tests/                 # pytest 用例（test_00~04）+ e2e_test.py
└── frontend/
    ├── app/                  # 仪表盘/凭证/账簿/报表/结转/设置/数据管理
    ├── components/           # Nav、凭证编辑器（智能补全）、UI 组件
    ├── __tests__/            # Jest + Testing Library 用例
    └── lib/api.js
```

## 月末处理流程（推荐）

1. 录入本月全部凭证
2. 【结转与结账】→ 计提折旧 / 摊销无形资产 / 计提工资 / 结转销售成本
3. 计提税金（城建税/教育附加）→ 免交增值税（如符合起征点）→ 计提所得税
4. 结转本期损益
5. 查看资产负债表/利润表/现金流量表确认无误
6. 结账（如有误可先反结账/反结转）

## 备份

- 界面【数据管理】→「备份数据库」下载单个 `.db` 文件
- 或直接拷贝 `backend/data/finance.db`
- 「从备份恢复」上传 `.db` 文件即可还原全部数据
