# Codex 交接文档（2026-10-26）

> 用途：对话上下文已很长，新开 Codex 对话时，把本文件内容作为开场背景发给 Codex，即可无缝接手。
> 项目就是 D:\industry-chain-research\，不要新建目录。

## 一、项目是什么

- 定位：安徽院材料事业部的「产业链信息协作平台」，不是新闻堆砌，而是**抓住产业链链路 + 可视化**做差异化。
  - 差异化核心：产业链长且分支多，平台按「链路/节点」组织信息，到任何一个小节点都能精准看到**上下游关系 + 该节点的精炼知识 + 同事贡献的条目**。
  - 信息要求：不能只拷贝网址内容，要有自己的理解/提炼（每条条目「提炼观点」必填）。
- 当前主攻产业：**屏幕产业链**（45 节点骨架已建）。
- 用户（老板）账号：zmjjkk（管理员，只有他能看到左侧栏「账号管理」）。

## 二、运行方式（重要）

- 代码/测试一律走 WSL，Windows PowerShell 只用来编辑文件。
- 启动 Flask：
  `wsl.exe -e bash -lc "cd /mnt/d/industry-chain-research && python3 app.py"`
- 校验数据：
  `wsl.exe -e bash -lc "cd /mnt/d/industry-chain-research && python3 ic_tools.py check"`
- 新版科技感界面 demo 入口：`http://127.0.0.1:5000/demo`（首页 / 也会进项目页）。
- 登录：先注册或由管理员在「账号管理」创建；demo 页面需登录后访问。

## 三、已完成的功能（截至 2026-10-26）

1. 项目迁移到 D:\industry-chain-research\（备份：~/industry-chain-research-backup-20261020.tar.gz，880K，勿动）。
2. 屏幕产业链 45 节点骨架 + registry 回填，ic_tools 检查通过。
3. 账号体系：注册 / 登录 / 登出 / 改密码；管理员用户管理页（/users，仅 admin 可见入口）。
4. 多项目框架：get_projects() 支持多产业，目前屏幕为主。
5. 图谱可视化：/chain-map、/demo 的树状图（echarts），节点可点开抽屉。
6. 节点精炼知识：/api/<project>/node/<id>（markdown 渲染）。
7. 同事条目（companies/news 两类）：
   - 提交接口 /api/<project>/node/<node_id>/rows（POST）
   - **防重复**：提交时后端查重，命中返回 409 + duplicates，前端弹「疑似重复」确认框，可强制提交。
   - 「提炼观点」必填（require_insight）。
8. 条目详情页 /<project>/entry/<entry_id>：可看完整字段、追评（followups）、纠错编辑（PUT）、删除（DELETE）、复核（review）。
9. 活动流 /<project>/activity。
10. 新版 demo（demo.html）：深色科技感、左侧树/图谱、搜索、节点抽屉、表单、防重复弹窗、toast。

## 四、进行中 / 最新反馈（下一步优先做）

1. **右侧抽屉精简（已完成 2026-10-26，demo.html）**：
   - 抽屉已改为 3 个 tab：概览（默认）/ 条目流 / 补充；底部常驻「＋ 补充一条信息」按钮（在「补充」tab 时自动隐藏）。
   - 概览：面包屑 + 4 格统计条（直接上游 / 直接下游 / 同事条目 / 最近更新）+ 链路定位卡片 + 精炼知识。
   - 条目流：条目默认收起，点击展开完整字段（提炼观点/字段/来源），并有「查看详情 / 纠错 / 删除 →」链接跳 /<project>/entry/<entry_id>。
   - 补充：表单移入该 tab，默认不显示；防重复弹窗逻辑保留。
   - 已通过 Jinja 解析 + node --check JS 语法检查（模板中的 Jinja 变量块除外）。
2. 界面整体继续加科技感、加交互（用户明确要求：画面丰富一点、别太简单）。
3. 曾讨论但未定：平台内置 AI（接入哪家模型未定）；公司 OA 服务器部署可行性未定（用户口头问过）。**当前不要主动做 AI 或部署**，等用户拍板。

## 五、禁止事项（沿用之前约定）

- 不碰 _archive 目录、不碰迁移备份包。
- 不 commit / 不 push，做完等用户验收，验收通过才进 git。
- 纯本地整理任务，禁止联网搜索编造内容；空白处填「待研究」。
- 以「已有材料的忠实下沉」为准，不要虚构企业、数据、新闻。

## 六、关键文件

- app.py：Flask 主程序（路由全在里）。
- auth.py：登录/权限辅助。
- rowstore.py：条目存储（companies/news、防重复逻辑）。
- ic_tools.py：数据校验工具（check/status）。
- templates/：demo.html（新版 demo 主页）、entry_detail.html（条目详情）、users.html、login.html、dashboard.html、chain_map.html 等。
- static/css/style.css、static/js/main.js、static/vendor/echarts.min.js。
- 协作说明：D:\桌面文件夹\产业链平台-Codex协作说明.md、项目内 CODEX-ONBOARDING.md / WORKFLOW-GUIDE.md / 同事使用说明.md。
