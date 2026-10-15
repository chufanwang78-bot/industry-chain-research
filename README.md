# 产业链研究工作台

> 安徽长三角产业创新研究院 · 材料事业部
> 项目路径: ~/industry-chain-research/

---

## 快速启动

```bash
cd ~/industry-chain-research
python3 app.py
```

然后浏览器打开 **http://localhost:5000**

---

## Web 界面功能

| 页面 | 功能 | 路由 |
|------|------|------|
| 📊 仪表盘 | 全局进度、统计图表、快速入口 | `/` |
| 🗺️ 产业链图谱 | 交互式树形图/关系图，点击节点查看详情 | `/chain-map` |
| 📋 节点管理 | 节点列表、搜索、筛选、状态管理 | `/nodes` |
| 📄 节点详情 | 查看/编辑研究内容、更新状态 | `/node/<编号>` |
| 📚 来源管理 | 资料来源台账、证据等级管理 | `/sources` |
| ⚙️ 工作流 | 11步研究流程、质量规则、质量检查 | `/workflow` |

### 核心交互
- **图谱页**: 顶部切换树形图/关系图，点击节点弹出详情浮层
- **节点详情**: 切换"查看/编辑"标签页，在线编辑 Markdown 研究内容
- **全局搜索**: 侧边栏底部搜索框，实时搜索节点
- **质量检查**: 工作流页一键运行，检查台账一致性

---

## 命令行工具（与 Web 界面共享数据）

```bash
cd ~/industry-chain-research

python3 ic_tools.py status          # 查看全局进度
python3 ic_tools.py tree            # 树状结构
python3 ic_tools.py next            # 待研究节点
python3 ic_tools.py show 05.01      # 查看节点详情
python3 ic_tools.py update 05.01 --status DONE
python3 ic_tools.py report          # 生成进度报告
python3 ic_tools.py check           # 质量检查
python3 ic_tools.py log "内容"       # 记录日志
```

---

## 项目结构

```
industry-chain-research/
├── app.py                      # Flask Web 应用（可视化工作台）
├── ic_tools.py                 # 命令行辅助工具
├── WORKFLOW-GUIDE.md           # 工作流总控指南
├── README.md                   # 本文件
├── config/
│   ├── workflow.yaml           # 工作流配置（产业分类体系）
│   └── nodes-registry.yaml     # 节点台账（自动维护）
├── templates/                  # Flask HTML 模板
│   ├── base.html               # 基础布局（侧边栏+导航）
│   ├── dashboard.html          # 仪表盘
│   ├── chain_map.html          # 产业链图谱（ECharts）
│   ├── nodes.html              # 节点管理
│   ├── node_detail.html        # 节点详情/编辑
│   ├── sources.html            # 来源管理
│   └── workflow.html           # 工作流指南
├── static/
│   ├── css/style.css           # 全局样式
│   ├── js/main.js              # 全局脚本（搜索等）
│   └── vendor/echarts.min.js   # ECharts 图表库
├── nodes/                      # 节点研究文件（Markdown）
│   └── 芯片/05-半导体材料/05.01-硅片衬底.md
├── sources/
│   └── source-index.yaml       # 来源台账
├── outputs/reports/            # 生成的进度报告
└── logs/workflow-log.md        # 工作日志
```

---

## 依赖

- Python 3.8+
- Flask (`pip install flask`)
- PyYAML (`pip install pyyaml`)
- ECharts（已本地化在 `static/vendor/`，无需网络）

---

## 工作流 11 步循环

```
选范围 → 看总图 → 选节点 → 讲原理 → 拆材料 → 找企业
→ 理证据 → 更新度 → 判深度 → 析需求 → 查覆盖
```

详见 `WORKFLOW-GUIDE.md`。

---

## 迁移到新产业

1. 修改 `config/workflow.yaml` 中的产业分类
2. 运行 `python3 ic_tools.py init --force`
3. Web 界面自动读取新数据

---

## 留给公司的说明

### 环境准备
```bash
pip install flask pyyaml
```

### 启动
```bash
python3 app.py
# 浏览器打开 http://localhost:5000
```

### 数据维护
- 节点台账: `config/nodes-registry.yaml`（YAML格式，可直接编辑）
- 研究内容: `nodes/` 目录下的 Markdown 文件
- 来源记录: `sources/source-index.yaml`
- 工作日志: `logs/workflow-log.md`

### 进行新产业研究
1. 复制项目目录
2. 修改 `config/workflow.yaml` 中的产业定义
3. `python3 ic_tools.py init --force`
4. 开始研究
