# 产业链研究工作平台 · 交接说明（给接手同事的 Agent 看）

> 用途：你的同事会把这份文档发给他的 AI Agent（如 Codex）。Agent 读完本文件即可接手这套代码，继续加功能、改界面、修 bug，不需要其他背景。
> 最后更新：2026-11-02。

## 0. 这是什么

安徽长三角产业创新研究院 · 材料事业部的「产业链信息协作平台」。

- 把一条产业链拆成若干「节点」，在网页上以树形图谱 + 节点详情展示。
- 同事打开网页即可查看，并在节点下「追加」自己掌握的企业/新闻条目（多人协作，追加式，不互相覆盖）。
- 数据全部是本地文件（YAML + Markdown + JSON），没有数据库，Flask 负责渲染成网页。
- 当前包含两个产业项目：**屏幕/显示**（已完成，参考）和 **存储芯片**（进行中）。

## 1. 技术栈

- Python 3 + Flask + Jinja2 + ECharts（ECharts 用本地 vendor，离线可用）。
- 依赖极少，见 `requirements.txt`：`flask`、`pyyaml`。
- 前端：`templates/` 里的 Jinja2 模板 + `static/css/style.css` + `static/js/main.js` + `static/vendor/echarts.min.js`。

## 2. 怎么跑起来

```bash
git clone https://github.com/chufanwang78-bot/industry-chain-research.git
cd industry-chain-research
pip install -r requirements.txt
python app.py
# 浏览器打开 http://localhost:5000
```

- 首次启动会自动生成 `config/.secret_key`（session 密钥），并自动创建默认管理员 `admin / admin123`。
- 登录后进入平台；新版科技感首页在 `/demo`（目前绑定「屏幕」项目）。
- 重要：改 `templates/` 后必须重启 Flask（Jinja 有缓存）；改 `config/*.yaml` 不用重启（每次请求都重读）。
- Windows 与 WSL/Linux 都能跑。并发文件锁依赖 `fcntl`，只有 POSIX（WSL/Linux）有锁；纯 Windows 上无锁（小团队够用，多人高频写入建议跑在 Linux/WSL）。

## 3. 目录结构

- `app.py` — Flask 主程序：页面路由 + JSON API（改功能主要在这）。
- `auth.py` — 账号体系：注册/登录/登出/改密码/管理员用户管理。
- `rowstore.py` — 条目数据存储：companies/news 追加、查重、纠错、删除、复核、变更日志。
- `ic_tools.py` — 命令行数据工具（status/tree/next/check/report/log）。
- `templates/` — Jinja2 页面模板：base、demo、dashboard、chain_map、nodes、node_detail、sources、workflow、activity、entry_detail、users、login。
- `static/` — css / js / vendor（echarts、marked）。
- `config/` — 配置与节点注册表（见第 4 节）。
- `nodes/<项目>/` — 研究正文 Markdown（四段式）。
- `rows/<项目>/` — 同事追加的条目 JSON（见第 4 节）。
- `sources/` — 来源台账。
- `tools/` — 搜索/抓取工具（bing_search.py、web_search.py、fetch_page.py）。

## 4. 数据文件约定（改动前必读）

- `config/projects.yaml`：多项目索引 + `current_project`（当前默认项目）。
- `config/nodes-registry.yaml`：**芯片**项目节点注册表（节点状态的单一事实源）。
- `config/nodes-registry-屏幕.yaml`：**屏幕**项目节点注册表。
- `config/nodes-registry-全芯片82节点-备份.yaml`：历史备份，勿动。
- `nodes/<项目>/*.md`：节点研究正文（定义 / 上下游 / 分类 / 代表企业 / 新闻 / 合作切入点 / 来源）。
- `rows/<项目>/<节点id>.json`：该节点同事追加的条目，结构为 `{"companies":[...], "news":[...]}`，每行带 `author` / `timestamp` / `entry_id`。
- `rows/<项目>/changelog.json`：只追加的变更日志。
- `config/users.json`：账号库（不在仓库里，首次运行自动建 `admin/admin123`）。
- `config/.secret_key`：session 密钥（不在仓库里，自动生成）。
- 规则：`nodes-registry.yaml` 是状态事实源；改 YAML 不用重启；改 `templates/` 要重启。

## 5. 关键路由与 API

页面路由：

- `/` 首页；`/login` 登录/注册；`/users` 账号管理（仅 admin 可见入口）。
- `/<project>/dashboard`、`/<project>/chain-map`、`/<project>/nodes`、`/<project>/node/<id>`、`/<project>/sources`、`/<project>/workflow`、`/<project>/activity`、`/<project>/entry/<entry_id>`。
- `/demo` 新版科技感首页（当前 `project="屏幕"`）。

JSON API：

- `GET /api/status`、`GET /api/tree`、`GET /api/graph`（键名是 `nodes`/`links`/`categories`，没有 `data` 键）。
- `GET/PUT /api/node/<id>`、`PUT /api/node/<id>/file`。
- `GET /api/search?q=`。
- `POST /api/<project>/node/<node_id>/rows`（追加条目，带查重，命中返回 409 + duplicates）。

## 6. 怎么改功能（给接手 Agent 的实操提示）

- 加/改页面：`app.py` 加 route → `templates/` 加模板 → `base.html` 侧边栏加入口（改模板后记得重启）。
- 搜索/筛选：已有 `GET /api/search`（app.py:564）和 `nodes.html` 的筛选；新增筛选要同时改后端 query 与前端模板/JS。
- 改条目逻辑：在 `rowstore.py`（追加 / 查重 / 纠错 / 删除 / 复核都在这）。
- 改界面：`static/css/style.css`、`static/js/main.js`、`templates/demo.html`。
- 图谱：ECharts；树图多个根必须包一个合成根 `id="__root__"`；图表键名 `nodes`/`links`/`categories`。
- 多项目：新功能必须项目无关（用 `project` 参数，不能写死「屏幕」或「芯片」）。

## 7. 质量红线（必须遵守）

- 不编造企业 / 产品 / 参数 / 新闻；拿不到可靠来源就写「待研究」。
- 条目「来源链接」和「提炼观点」必填。
- 研究内容只写数据文件，不要写进代码。
- 不碰 `_archive` 目录和「…备份」文件。

## 8. 改完怎么验证

```bash
python ic_tools.py check    # 数据质检
python ic_tools.py status   # 进度
python ic_tools.py tree     # 树状
python app.py               # 起服务手动点一遍
```

## 9. 更多背景

- `README.md`、`CODEX-ONBOARDING.md`、`WORKFLOW-GUIDE.md`、`同事使用说明.md`。
- 研究方法论见 `EXECUTION-PROTOCOL.md`。