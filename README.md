# 招聘岗位要求抓取器（SAP MM 示例）

从猎聘抓取 SAP MM 相关岗位，按条件筛选后把每个岗位的**“职位介绍”全文**汇总成 Excel。
本仓库同时包含抓取程序源码、样例数据与自动校验脚本。

## 本次结果

- `猎聘SAP-MM岗位要求汇总.xlsx`：84 行（岗位），覆盖 54 家公司
- 条件：关键词 `SAP MM`；经验 3-5 年；公司规模 >1000 人；地点 上海/北京/深圳/广州/杭州/苏州/成都/武汉/大连；同一公司最多 3 行
- 共 4 个工作表：岗位需求明细 / 公司与岗位汇总 / 筛选条件与统计 / 职位清单
- 明细页 13 列，`需求内容` 为猎聘“职位介绍”栏全文（保留原始换行）
- 自动校验 16/16 项通过（见 `validation_report.txt`）

## 目录

```
job_scraper/
├── cli.py, web.py               # 命令行 / 本地网页两种入口
├── models.py, filters.py        # 条件解析与筛选
├── scraper.py                   # 搜索→筛选→详情→汇总→每公司限量（带缓存）
├── excel_export.py              # 4 个工作表的 Excel 导出
├── jd_parser.py                 # JD 清洗与拆分（用于统计与相关性判断）
├── validate_output.py           # 结果自动校验
├── platforms/liepin.py          # 猎聘适配器（平台层已抽象，可扩展）
└── README.md                    # 详细说明
```

## 使用

```powershell
# 网页界面
python web.py            # http://127.0.0.1:8765

# 命令行
python cli.py -k "SAP MM" -y 3-5 -c 1000+ -l "上海,北京,深圳" -n 100 --max-per-company 3
```

依赖：Python 3.10+、openpyxl。

## 免责声明

数据来自招聘网站公开页面，仅供个人求职分析与学习使用；请遵守目标网站服务条款并控制请求频率。
