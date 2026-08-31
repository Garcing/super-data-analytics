# SDA MCP 服务全工具 QA 测试报告(2026-08-26)

> 测试对象:hermes 服务器线上 SDA MCP 服务(19 工具)。
> 方法:9 个 subagent(8 只读并行 + 1 终端破坏性),44 题,约 250 次真实 MCP 调用。每个 subagent 上下文只含 MCP 工具描述 + Skill 列表 + 测试题与安全红线,读不到本地代码与协调者会话——同时检验功能正确性与"裸接入 Agent 只凭 tool list + Skill 能否正确使用"。
> 确定性计算(contribute/impact/forecast/chart)全部先独立手算再调用对账;错误消息原样留档;关键 bug 由协调者在服务器日志层面二次定位根因。
> 敏感测试经用户授权:1 次真实图片生成(计费)、1 次真实文档覆盖(已恢复)、1 次全量 sync。

## 总体结论

**数学与渲染内核质量过硬,只读安全可靠;但"错误处理"系统性缺失放大了一切问题,且 HTML 报告发布已静默失效 6 周。**

| 领域 | 结果 |
|---|---|
| contribute / impact / forecast 数值 | ✅ 全部手算对账通过,零数值错误 |
| chart 渲染 | ✅ 14 图型、14 张看图核对零中文乱码,比例/正负色全对 |
| SQL 只读安全 | ✅ 机制级验证(`transaction_read_only=on`,INSERT 被拒后核验 0 行写入) |
| sync / 语义层 | ✅ 全量重建单次成功,planned=actual 逐项一致,重建后检索复检全过 |
| Power BI 真实链路 | ✅ schema/DAX/度量值全通(2 个真实语义模型) |
| 飞书文档 / 图片生成 | ✅ 主链路可用(各有写入污染/契约问题) |
| HTML 报告发布 | ❌ **P0,100% 失败,自 2026-07-11 起** |
| 错误信息质量 | ❌ **P0,全工具裸错误** |

## P0(2 个,均已定位 file:line)

### P0-1 `report_html_publish` 自 2026-07-11 起全部失败

第一波 agent 8 次调用(4 种载荷形态,含契约完整形态)全挂,协调者复现 2 次,服务器日志定位出两个独立缺陷:

- **缺陷 A** — `sda_mcp/skills/building_reports/html_reports.py:87`:`_build_index_entry` 中 `"summary": (body.get("summary") or {}).get("overall", "")` 假设 `summary` 是 dict,传字符串直接 `AttributeError: 'str' object has no attribute 'get'`。report 参数 schema 为 `additionalProperties: true`,未约束 summary 结构——合法输入崩掉服务。
- **缺陷 B** — `html_reports.py:116`:summary 为对象时走到乐观锁,`ExternalAPIError: 索引乐观锁重试 5 次仍失败: Vercel Blob 条件写失败(ifMatch 不匹配,索引已被他人改写)`。日志显示索引内容从公共 CDN URL 带 `?v=2026-07-11T09:01:04.000Z` 陈旧缓存读取——该时间戳恰是最后一份成功报告(funnel-analysis-20260711)的索引写入时间,即从那天起 ifMatch 永远对不上,确定性死循环。
- **副作用**:失败前报告 JSON 已先上传 Blob(日志 `PUT html-reports/qa-*.json 200 OK`)→ 每次失败留孤儿对象。测试遗留 `html-reports/qa-2026-08-26-verify.json`、`qa-2026-08-26-verify2.json` 两个待服务端清理。

关键日志证据(缺陷 B 完整链):
```
PUT https://vercel.com/api/blob/html-reports/qa-2026-08-26-verify.json "HTTP/1.1 200 OK"
GET https://vercel.com/api/blob/?url=html-reports-index.json "HTTP/1.1 200 OK"
GET https://o2v8qrfoxqnbqwk4.public.blob.vercel-storage.com/html-reports-index.json?v=2026-07-11T09:01:04.000Z "HTTP/1.1 200 OK"
ExternalAPIError: 索引乐观锁重试 5 次仍失败: Vercel Blob 条件写失败（ifMatch 不匹配，索引已被他人改写）
```

### P0-2 全工具内核错误被吞:调用方永远看不到原因

横切 bug,5 个 agent 独立撞上(约 40+ 次裸错误)。内核抛出的 `SkillError` 消息本身可操作(日志实证):

- `DataSourceError: 无法连接 Hologres（检查 VPN/白名单/凭证）: connection failed: connection to server at "127.0.0.1", port 15432 failed: server closed the connection unexpectedly`
- `DataSourceError: SQL 执行失败: permission denied for schema ads_bu`
- `DataSourceError: SQL 执行失败: cannot execute INSERT in a read-only transaction`
- `DataSourceError: SQL 执行失败: syntax error at end of input`

但工具层未捕获,MCP SDK(`mcp/server/mcpserver/tools/base.py:210`)统一包成 `UnexpectedToolError("Error executing tool <名>")`——客户端只见工具名。pydantic 入参校验错误却能完整透出(含字段名、约束、文档链接),体验割裂。

**直接后果**:语法错/表不存在/权限/连接抖动/破坏性校验等 10+ 类失败完全不可区分(SQL 组 agent 盲试 10+ 次才定位一个问题);publish P0 因此被掩盖 6 周。**修复点:`sda_mcp/tools/*` 统一 catch `SkillError` 子类转为保留消息的错误类型。**

## P1(功能缺陷,9 个)

| # | 问题 | 证据/根因 |
|---|---|---|
| 1 | `retrieve_cypher` 只要 RETURN 图元素(`RETURN n`、`properties(n)`)必挂,`LIMIT 10` 也挂,与体积无关 | 对照实验:标量/逐属性/labels()/type()/count()/字面量 map/list 全正常;错误一律 `Error executing tool retrieve_cypher` 零细节。Cypher 最标准写法不可用且无文档警示 |
| 2 | 飞书 docx **导出接口**把 `"` `&` `<` `>` HTML 实体化(勘误:初版误判为写入路径) | 探针实证(2026-08-27):docx 存储层干净(list_blocks 文本原样),`docs/v1/content` 导出时先实体化(`&#34; &amp; &lt; &gt;`)再做 markdown 反斜杠转义 → 机器读取通道拿到 `\&\#34;` 残留;SQL 模板 `>=` 变 `&gt;=` 不可执行。已修复:读取侧解码,读写往返幂等 |
| 3 | `sda-vpn` 转发器间歇断连 → sql_query ~11% 抖动(4/36 次健康路径失败,重试即恢复) | 日志多次 `psycopg.OperationalError: connection to server at "127.0.0.1", port 15432 failed: server closed the connection unexpectedly`;容器却显示 healthy,看门狗失明 |
| 4 | `sql_schema` 对不存在表/逻辑语义表静默返回 `columns:[]` 不报错 | 两个 agent 独立踩中(`public.no_such_table_xyz` 与 `semantic.fact_user_period_lifecycle`);与 querying-data Skill"会报 relation does not exist"描述相反(文档漂移);宽表输出无裁剪,4 表一次 78,435 字符溢出转存 |
| 5 | forecast 不校验 grain 与日期间隔 | 月度数据标 grain=day 静默输出逐日日期(2025-12-02/03/04),"每月+3"被标成"每日+3",结论失真无警告 |
| 6 | forecast 长程外推无护栏 | 12 点历史 horizon=200 照跑(外推至 2042 年),confidence 仍 high、区间零宽不展宽、无警告 |
| 7 | forecast/contribute/impact 所有校验拒绝一律裸错误 | 1 点序列、重复日期、horizon=0、log 非正值、baseline=0、分母=0、success>n、cost=0、MDE=0……全部只返回 `Error executing tool <名>`,无一处说明原因(P0-2 受害者) |
| 8 | chart heatmap 默认 `value_format=".2g"` | 120/150/110 渲染为 `1.2e+02/1.5e+02/1.1e+02`,业务图表不可读(可用 options.value_format 规避,默认值欠妥) |
| 9 | chart 复杂图型 spec 契约不可发现 | waterfall 功能正常(正确契约 `start_value` + 带符号 items,图表组看图全对),但契约只在本地 references,工具 schema 不展开;端到端 agent 两种直觉写法(x/y+is_total、category/value/measure)均裸错误失败;visualizing-data Skill 承诺"ContractError 指向具体字段/行"与现实相反 |

环境项:**ads_bu schema 无权限**(`permission denied for schema ads_bu`)——SQL 组发现的"FOREIGN 表不可读"真因,9 种查询形状 0 成功;若该表受治理需补授权。

## P2(可用性/文档问题,按域)

**统计口径未披露**
- `sample_size_rate` 的 MDE 实测为绝对百分点差(p1=p0+MDE),但工具描述/返回/Skill 均未说明,也不回显推导用 p1;按相对提升理解样本量差约 **93 倍**(baseline 0.10、MDE 0.02:3841/臂 vs ~356,338/臂)。
- ab_rate 混用三种区间口径不标注:p 值=合并比例 z 检验、lift CI=非合并 Wald、单组率 CI=Wilson score。
- contribute ratio 分组 mix 贡献是协方差形 Σ(p_i0−P̄0)·Δw_i(与教科书常见形 Σp_i0·Δw_i 分组值不同,聚合等价),未文档化。
- ab_mean 不返回 t 统计量与自由度;使用正态近似(有 warning)但小样本近临界值时可能翻转结论。
- forecast 回测为"单起点 3 步不滚动"语义(数值反推证实),与常见滚动回测直觉不同,未写明。

**语义检索**
- 顶层 `score` 字段 = vector_score 而非排序依据 fusion_score,hybrid 首条 score(0.824)低于第二条(0.839),易误判"排序错乱",未文档化。
- 输出体积无控制:top_k=5 一次约 56KB, top_k=20 约 200KB;context 邻居 items 顺序非确定(无害)。
- 纯 vector 下"复购人数"排第 2(复购率 0.839 > 0.824),正确第一名依赖 hybrid 的 exact_match 通道——默认 hybrid 必要,文档可补充说明。
- `ORDER BY` 不存在属性静默按 null 排序不报错,属性名拼写错误无保护(Neo4j 原生语义)。

**Power BI**
- 返回双重 JSON 编码:JSON-RPC 信封内 text 块再包一层 `\uXXXX` 转义 JSON 字符串,中文全转义,费 token 且易截断。
- 错误信封三态不一致:powerbi_schema 返回 JSON-RPC error 对象(code -32004);powerbi_query 伪 GUID 返回 result.content + isError:true 嵌套 Answer/Error;DAX 语法错误返回纯文本且**无 isError 标记**(自动化调用方可能把错误文本当数据)。
- `max_rows` 截断完全静默:TOPN(500) + max_rows=5 恰好回 5 行,无 rowCount/总数/truncated 标记。
- "模型不存在"与"无权限"合并为同一文案(Power BI 原生行为,可接受);带 RootActivityId 可提工单。

**SQL**
- numeric 聚合值以字符串返回(保精度)、列类型为 PG OID 编码、timestamptz 统一序列化为 UTC——均未在工具描述或 Skill 说明。
- 大表 count(*) 两次客户端超时(`The operation timed out.`),无服务端防护或行数预估指引落地;LIMIT 截断的目录列表无"不完整"提示。
- 返回结构本身优秀(columns+rows 对象数组+row_count 三件套、不自动截断、中文别名/中文值完美往返、NULL 处理正确)。

**报告与图片**
- report_html_list 排序语义 created_at/updated_at 降序在现有数据下不可区分;时间戳毫秒位不统一(`...Z` 与 `...000Z` 并存);无数量上限说明。
- 图片生成 seed 被静默接受不回显,复现性无法从返回侧确认;URL 为 24h 预签名直链(交付需提醒时效)。
- SVG 以二进制内容块返回且不上传 Blob(符合设计),但客户端必须落盘才能查看。
- chart:dpi 不改变输出像素尺寸(72/144/300 全部 1200x720,仅改物理尺寸/相对字号),与"清晰度参数"直觉相反未说明;轴标题默认取原始字段名(英文),中文交付需手动 axis_labels;pareto 累计曲线默认英文图例;horizontal_bar 首行绘于最下(matplotlib 惯例)。
- 成功调用时图片内容块 URL 与文本块声称的 Blob URL 可能不同源(ufileos 签名地址 vs vercel-storage 并存),来源未说明。

**飞书文档往返损耗**
- docx 标题块不受"清空正文"影响:按导出原文整体写回会造成标题重复,恢复类操作需手工去掉首行 H1。
- 代码块语言标记大写化(`sql`→`SQL`);空引用块行(`> `)被丢弃;嵌套加粗/行内代码边界星号部分转义且不可通过重写复原。
- 导出侧对 `+` `.` `(` 等做装饰性反斜杠转义,但多轮往返不累积(稳定在单层)。
- 伪造 token 错误路径快速失败不挂起(好),但报错零细节。

**语义层内容治理**
- 5 个报告模板中 3 个名为"占位符1/2/3"且共用同一测试文档 token,治理内容未填实。

**Skill 漂移(仅 2 处)**
- visualizing-data:"错误信息可操作:指明字段名、行号、实际值"——与现实(裸错误)相反。
- querying-data:sql_schema"数据库报 relation does not exist 是预期现象"——实际静默空列。
- 其余(orchestrating-analytics / retrieving-context / predicting-trends / evaluating-impact / validating-analyses)与工具行为零漂移,且 retrieving-context 提前预警了全部三个坑(逻辑表不要直接 sql_schema、SQL 文档剥 token、字段格式)——Skill 质量是亮点。

## 降级/澄清的初判

- **"非法枚举被静默改写为合法值执行"(PBI 组 P1)→ 非服务端 bug**:协调者亲自复测,非法枚举(method="abc")根本发不出去——调用方(MCP 客户端/模型)受工具 schema 枚举约束自动收敛为合法值("add")。服务端枚举校验经此通道不可测,降级为测试方法学观察。
- **"waterfall 图型走不通"(e2e 组)→ 功能正常**:图表组用正确契约一次渲染成功且看图全对;重新定性为 P1-9 契约不可发现。
- **"外部表(FOREIGN)不可读"→ 真因是 schema 权限**:日志 `permission denied for schema ads_bu`,与 FOREIGN 表类型无关。

## 测试现场状态(全部还原)

- ✅ 飞书《Markdonw格式测试报告》(token `V6TYdWScDoms5axrSmkcM5FHn0b`)已恢复原文,逐字核对一致,仅 3 处转换器级微小差异(空引用行、sql 大小写、嵌套加粗边界)。
- ✅ 全量 sync 执行 1 次成功(未超时未重试),图最终 211 节点/498 关系/10 约束/10 向量索引+10 全文索引/211 embedding,与 dry_run 计划完全一致,重建后检索复检(exact_match 命中首条)全过。
- ✅ 三份正式报告(funnel-analysis-20260711 / report-user-growth / report-region-sales)未受任何影响;qa- 测试报告未入索引。
- ⚠️ Vercel Blob 遗留 2 个测试孤儿对象(`html-reports/qa-2026-08-26-verify*.json`)待服务端清理。
- 💰 图片生成真实计费 1 次:request_id `02178772997009553952e287ddd1b7d9109cd0048896ba053bb35`,doubao-seedream-5-0-pro-260628,2816×1584,17,424 output tokens。

## 修复优先级

> **修复进度(2026-08-27)**:第 1-4 项已修复部署(commit c4b2fba);第 5 项中的 sql_schema 护栏、forecast grain/horizon 护栏、heatmap 默认格式、图型契约披露、MDE 披露、powerbi 解码/信封、两处 Skill 漂移已修复部署(commit 3476387,基线 204 passed)。剩余 P2 长尾见各节。
>
> **修复进度(2026-08-31)**:chart 元数据已补结构化通道——工具改为 `Annotated[CallToolResult, ChartOutput]`,structuredContent 返回 `{format,width,height,url}` 并在 tools/list 广告 outputSchema(此前尺寸/URL 只埋在散文 text 块里,程序侧需正则抠取,即 P2 长尾 ③ 的元数据半边;maas-log-prod 那个 URL 是客户端 harness 对 image 块的中转托管,属客户端行为,不在服务端修复范围)。模型侧行为零变化(image 块+散文 text 块原样保留)。同日 report_image_generate 同样从裸 `-> CallToolResult` 升级为 `Annotated[CallToolResult, ReportImageOutput]`,获得 outputSchema 广播与运行时校验(TypedDict 按内核 dataclass 真实可空性建模:created/request_id/url/size/error 可空,usage 开放 dict)。

1. **错误透出**(P0-2):tools 层 catch `SkillError` → 结构化错误。一处模式,19 工具受益,让后续所有问题可诊断。
2. **publish 修复**(P0-1):summary 兼容字符串 + 索引读取绕开 CDN 陈旧缓存;清理孤儿 Blob。
3. **retrieve_cypher 图元素序列化**(P1-1)与**飞书导出实体化污染**(P1-2,后经探针更正为导出侧而非写入侧)。
4. **VPN 转发器稳定性**(P1-3):openvpn keepalive/socat 重连 + `HologresClient` 连接级重试。
5. 其余 P1/P2 按表格顺序,多数是加校验、加提示、补文档的小改动。

---

# 附录 A 检索组报告(Q1–Q5)

## Q1 默认 hybrid 检索"复购人数是什么口径"
- 调用:`retrieve_search(question="复购人数是什么口径")`(默认 hybrid, top_k=5),秒级。
- 期望 vs 实际:首条 `label=指标`、`指标名称=复购人数`、`指标ID=repurchase_users`、`指标定义="用户在同一品类范围内复购了下一个正式营的人数"`、`分子表达式=sum(link."是否复购")`,`retrieval.exact_match="复购人数", exact_rank=1`。结构完整:properties(13 字段)、context 按邻居类型分桶(每桶 items/total/truncated)、retrieval 块含 strategy="hybrid_rrf"、fusion_score、vector_score、fulltext_score、vector_rank、lexical_rank、exact_rank。
- **PASS**。证据:首条 `fusion_score=0.0519, vector_score=0.8244, fulltext_score=3.9969`;context 表桶 total=1、维度组桶 total=5。
- 可用性:小瑕疵——顶层 `score` = vector_score 而非排序依据 fusion_score(见 Q2)。

## Q2 参数变体对比
- vector vs hybrid:vector 首条是"复购率"(0.8393),复购人数退居第 2(0.8244);hybrid 靠 exact_match 提到第 1。vector 结果无 retrieval 证据块,与文档一致。
- top_k=1:恰 1 条;top_k=20:满 20 条(19 指标+1 表),表中第 3 名为 `表`,其 context.指标桶 total=35, truncated=true,截断标志真实工作。
- top_k=0 / 21:pydantic 拒绝(错误原文):
```
Error executing tool retrieve_search: 1 validation error for retrieve_searchArguments
top_k
  Input should be greater than or equal to 1 [type=greater_than_equal, input_value=0, input_type=int]
```
- targets=["指标"]:5 条结果全部 label=指标,白名单生效(白名单只过滤结果实体,context 仍展示表/维度组邻居,合理)。
- **PASS**(附 SMELL:score 字段语义)。可用性:输出体积大(top_k=5 约 55.7KB 被客户端持久化,top_k=20 约 200KB);context 邻居 items 顺序不稳定(无害)。

## Q3 schema 与图数据交叉核对
- `retrieve_schema()` 声明 10 标签/8 关系;图中实测:指标 65、表 58、维度 55、报告模板 5、数据看板 2、业务线 1、业务板块 8、业务小点 2、维度组 9、表关系 6,共 211 节点,无 schema 外标签、无多标签节点;按(起点,类型,终点)聚合的 8 种关系组合与 schema 逐一吻合(常用维度 243、使用 96、包含 65、来源于 55、启用 26、参与 13)。
- 1-hop:repurchase_users 邻居 = 常用维度→维度组×5 + 使用→表×1,与 Q1 context 一致。
- **PASS**。`retrieve_schema` 与实测零漂移。

## Q4 retrieve_cypher 边界
- 语法错误 `MATCH (n RETRN n`:仅返回 `Error executing tool retrieve_cypher`,零细节。
- ORDER BY 不存在属性:不报错,优雅按 null 排序返回(拼写错误无保护)。
- `MATCH (n) RETURN n LIMIT 2000`:失败;定位实验证明与体积无关——`RETURN n LIMIT 10` 同样失败,`RETURN properties(n)`(哪怕单节点)也失败;标量、labels()、type()、count()、字面量 map/list 全部正常。**凡 RETURN 中出现图元素对象或 properties() 结果一律失败。**
- **FAIL**(两缺陷:图元素序列化失败;错误信息不可操作)。可用性:必须养成逐属性 RETURN 的写法,工具描述与 Skill 均未警示。

## Q5 报告模板检索与文档读取
- `retrieve_search("有哪些报告模板")` 命中全部 5 个模板实体(与图中计数一致),URL链接属性为"显示文本+换行+URL",可剥出 docx token,与 Skill 描述一致。
- 真实文档(`IGcQdtVdNo9mgTxGspPcSaMInTb`,平台治理经营健康数据播报)秒级返回完整 markdown:监控退费/复购/完课/投诉周环比,正式营健康阈值退费率≤2%、复购率≥40%、完课率≥80%。
- 内容层观察:markdown 转义残留(正文 `\&amp;\#34;`、`\&amp;amp;`、`\-\`、`\(本周 \- 上周\)`,表格转原始 `<table><tbody>` HTML);5 个模板中 3 个名为"占位符1/2/3"共用同一 token。
- 伪造 token `doccnFakeToken000`:毫秒级快速报错不挂起,但零细节(`Error executing tool retrieve_doc_read`),无法区分 token 不存在/无权限/参数非法。
- **SMELL**。

# 附录 B SQL 组报告(Q6–Q10)

共 36 次 sql_query(18 成功/16 裸错误/2 客户端超时)+ 4 次 sql_schema(全成功)。

## Q6 表盘点
- information_schema 查询返回 50 行触顶截断(无提示);GROUP BY 补查:22 个 schema、约 1400+ 张表(ads_bi 5、ads_bu 1、app_report_log 301、dw_ops 393、dw_cdp 315、xqd_data_analysis 140 等)。**PASS**。

## Q7 sql_schema 内省与交叉核对
- `ads_bi.ads_bi_xqd_cdp_user_life_cycle`(39 列)与 `ads_bu.ads_xqd_increase_path_session_ab_test_data`(85 列):sql_schema 的序号/字段名/数据类型与 information_schema.columns 逐列吻合,且额外返回默认值/可空/主键/中文注释。
- `public.no_such_table_xyz`:静默返回 `{"tables":[{"schema":"public","table":"no_such_table_xyz","columns":[]}]}`,无任何报错。
- **SMELL**(核对 PASS;错误路径缺陷)。

## Q8 业务聚合与结构
- dw_trade.dim_xqd_trade_sku 聚合(GROUP BY/sum/avg/LIMIT):columns 含 dataTypeID(25 text/20 bigint/1700 numeric)、rows 对象数组、row_count=7;中文别名完整往返(列元数据、行键、GROUP BY/ORDER BY 引用均正常);NULL 聚合返回 JSON null;numeric 以字符串返回。
- 重要波折:ads_bu 表 9 种查询形状(含 `SELECT sku_id ... LIMIT 1`)全部失败,与 dw_trade 背靠背对照确认确定性不可读(真因见 P1 环境项:schema 无权限);ads_bi 首读遇一次失败重试成功(间歇抖动)。
- **PASS**(功能)。

## Q9 错误路径四连
- (a) 语法错误、(b) 表不存在、(c) INSERT:全部被拒但返回同一句零信息裸错误 `Error executing tool sql_query`。(c) 机制验证:事后 count WHERE sku_id=999999999999 返回 0(未写入);`current_setting('transaction_read_only')='on'` 证明语句包在显式只读事务中。
- (d) 301 分区大表 count(*) 两次客户端超时(`The operation timed out.`);窄列 LIMIT 1000 秒级成功,约 16KB。
- **SMELL**((c) 拒绝与只读性 PASS;(a)(b)(d) 错误质量缺陷)。

## Q10 兼容性
- SELECT 1+1=2;COALESCE/NULLIF 正确;current_date='2026-08-26';date_trunc('month')='2026-07-31T16:00:00Z'(+08 时区正确);窗口函数 row_number() PARTITION/ORDER/NULLS LAST 全正常。timestamptz 序列化为 UTC ISO。**PASS**。

# 附录 C PowerBI+sync 组报告(Q11–Q16)

## Q11 发现真实模型
- retrieve_search("数据看板")首查命中,cypher 全量核验:平台治理经营看板 `c85590e6-770f-411f-a716-10d0147ad68b`、超级VIP项目看板 `3041d238-c8dc-4b8d-aff7-8c262c631b6c`,与 sync dry_run fetch 计数(数据看板:2)一致。**PASS**,秒级。

## Q12 powerbi_schema
- 真实 ID:23 张表(度量值表 3 张纯度量约 90 个:GMV/流水/NPS/投放ROI/复购率/退费率/质检误判率等;日期表 27 列含层级;员工架构表 48 列;用户全链路明细表 100+ 列……),ActiveRelationships 17、Inactive 2,附 semanticModel 元数据。10–30 秒档。**PASS**。
- 伪 GUID:明确实体不存在错误(带 RootActivityId、error-code PowerBIEntityNotFound、status-code NotFound)。**PASS**。备注:返回双重 JSON 编码(JSON-RPC 信封内 text 再嵌 `\uXXXX` 转义 JSON 字符串)。

## Q13 powerbi_query 正反路径
- (a) 真实 ID `EVALUATE ROW("test", 1)` → `rows:[[1]]` Int64,秒级;(b) `[GMV]` → `2827420973.0399966`,5–10 秒档;(c) 伪 GUID+非法 DAX:artifact 校验先于 DAX 解析(DurationMs:0);(d) 真实 ID+`EVALUATE SELCT 1`:服务端语法错误完整透传含行列位置,但为纯文本内容返回且未见 isError 标记。错误层级清晰:artifact→DAX 解析→执行。**PASS**(信封形态问题见 P2)。

## Q14 max_rows 截断
- 真实 ID `EVALUATE TOPN(500, '日期表')` + max_rows=5:恰好返回 5 行(2026-04-01~04-05),executionResult 无 rowCount/总数/truncated 标记,截断完全静默。**SMELL**。

## Q15 sync(dry_run=true)
- 约 10 秒档返回:`validated:true, warnings:[]`;fetch:业务线1/业务板块8/业务小点2/数据看板2/指标65/维度组9/维度55/表58/表关系6/报告模板5(合计 211);planned:clear_graph、约束10、关系8、向量索引10、全文索引10、regenerate_embeddings。**PASS**,与工具描述吻合。

## Q16 入参卫生
- (a) `sql_query(sql="")`、(b) `retrieve_search(question="")`:pydantic minLength 拦截,错误完整可操作(string_too_short + 文档链接),无堆栈泄露。**PASS**。
- (c) `contribute(method="abc")`:非法枚举从未以 "abc" 到达服务器,5 次调用全部以 method="add" 执行;第 5 次被权限分类器拦截,拦截消息明确指出"意图是 abc、实际是 add"。服务端枚举校验路径经此通道不可观测。**SMELL**(协调者复核:调用方 schema 枚举约束所致,非服务端 bug)。

# 附录 D contribute/impact 数学组报告(Q16–Q25)

全部即时返回,无超时。

## Q16 contribute add 基础
- 1000→1150,三分项 500→570/300→310/200→270:贡献 70/10/70、Δ=+150、residual=0、share 0.466667/0.066667/0.466667、relative_contribution 0.07/0.01/0.07。direction"同向解释"口径清晰。**PASS**。

## Q17 add 退化与不一致
- (a) 全不变:全零贡献守恒,Δ=0 时 contribution_share=null 而非 0/0(Skill 承诺落实)。**PASS**。
- (b) items 合计 999≠total 1000:sum_contribution=151、residual=-1、warning"分项贡献量之和不等于总体变化,请检查分项是否互斥且完整"。显式暴露未静默。**PASS**。残差符号=总变化−分项合计,自洽。

## Q18 multiply(LMDI)
- 访客 10000→11000、转化率 0.05→0.044、客单价 200→220:V0=100000、V1=106480、Δ=+6480;工具返回 9836.5917/−13193.1834/9836.5917,sum=6480.000000000002,residual=−2e-12(浮点噪声级);转化率"反向抵消"。手算对数份额复算一致(1.5179925)。**PASS**——标准 LMDI,守恒精确。

## Q19 multiply 边界
- baseline=0:拒绝但裸错误 `Error executing tool contribute`;负数因子:同样;两因子不变:Δ 全归访客数,其余精确 0。**SMELL**(拒绝正确、报错裸)。

## Q20 ratio
- X 400/1000→480/1200、Y 100/500→90/450:总体率 1/3→19/55,Δ=2/165=0.012121212121,sum_contribution 一致、residual=0,两组率不变→within=0、interaction=0、结构=+0.0121212。**PASS**。mix 采用协方差形(约定见 P2)。单组:全 within。分母 0 组:裸错误拒绝。**SMELL**。

## Q21 ab_rate
- control {10000,1000} vs treatment {10000,1100}:p_value=0.021075(手算合并 z=2.3068→0.0211)、CI=[0.001504,0.018496](手算非合并 Wald 逐位一致)、absolute_lift=0.01、relative_lift=0.1、significant=true。单组率 CI 经复算为 Wilson score。**PASS**。
- 边界:success>n、n=0:裸错误拒绝;双零成功:rate 0、lift 0、**relative_lift=null**(与 Skill"对照基率为 0 时相对 lift 无定义"一致)、p=1、CI={0,0}、无 NaN。**PASS**(p=1/CI=[0,0] 为 0/0 约定处理,建议加 warning)。

## Q22 ab_mean
- control {100,50,10} vs treatment {120,53,12}:mean_difference=3、**cohens_d=0.269388(手算精确一致)**、p_value=0.043114、CI=[0.092904,5.907096](=3±1.95996×1.48324 正态 z 区间)、significant=true、warning"均值检验使用正态近似;小样本或重尾分布建议做专项检验"。
- **PASS(数值)**。注:出题参考"t≈21"有误(正确 t≈2.02、p≈0.043,agent 复算纠正);工具用正态近似而非 Welch-t(p 0.0431 vs 0.0446),warning 已披露;不返回 t 与 df。
- 边界(双零方差):p=1、significant=false、cohens_d=null、CI=[3,3](零宽且不含 0)——内部信号矛盾,无零方差专项告警。**SMELL**。

## Q23 did
- T 100→130、C 100→115:treatment_change=30、control_change=15、did_effect=15、relative_did_effect=0.15(15/处理组基期,自洽),warning 提示不自动证明平行趋势。**PASS**。

## Q24 roi
- 300000/100000:net_benefit=200000、roi=2、profitable=true——确认 (b−c)/c 口径,与 Skill 一致;50000/100000:roi=-0.5;cost=0:裸错误拒绝。**PASS**(口径自解释;cost=0 报错裸)。

## Q25 sample_size_rate
- baseline 0.10、MDE 0.02、alpha 0.05、power 0.8:`sample_size_per_group=3841`。手算:绝对差解释(p1=0.12)≈3841/臂;相对解释(p1=0.102)≈356,338/臂——工具匹配绝对差解释,但 MDE 语义未在任何地方披露、不回显 p1(详见 P2)。
- 边界:MDE=0、baseline=0、baseline=1、alpha=0:全部裸错误拒绝。**SMELL**。

# 附录 E forecast 组报告(Q26–Q29)

共 23 次调用,耗时均 1 秒档(horizon=200 约 1–2 秒),无超时。

## Q26 线性外推
- L(12 点月度等差+3)/month/horizon=3/linear_trend:预测 136/139/142(=133+3n),区间 [136,136] 等零宽,backtest {holdout:3, mae:0, mape:0, rmse:0},confidence=high。auto_baseline 自动选 holt_linear(理由 "recent holdout MAPE is 0"),数值相同。**PASS**(完美拟合时区间退化零宽,见 P2)。

## Q27 季节外推
- S(24 点 [90,100,120,160]×6)/month/season_length=4/seasonal_naive:2026-01/02/03 = 90/100/120,**相位对齐正确**。linear_trend 同数据:手推 OLS 斜率 0.6、截距 110.6,预测 125.0/125.6/126.2 与工具逐位一致;误拟合但如实报告(backtest mae=20.03、mape=15.1%、confidence 降 medium)。区间下界 92.61 未覆盖下季真值 90(错模下区间偏窄实例,技能文档已声明局限)。**PASS**。

## Q28 模型全集
- naive=133、moving_average=130(近3点均值,窗口3)、weighted_moving_average=131(权重1:2:3反推吻合)、exponential_smoothing=128.52(α≈0.36–0.38 合理)、holt_linear=136、linear_trend=136、log_linear_trend=137.288997(手推 OLS-on-logs e^4.922086=137.29 逐位吻合)、auto_baseline=136(选 holt_linear)。8/9 正常。
- **seasonal_naive 未传 season_length 即裸失败**:`Error executing tool forecast`,无任何原因(推断:12 点月度无法自推或自推后不足 2 周期,抛未包装异常)。显式传 season_length=4 可正常工作。
- 另核验:回测语义为单起点 3 步不滚动 holdout(用 naive 的 mae=6/rmse=6.480741=sqrt(42) 反推证实)。
- **SMELL**。

## Q29 边界与脏数据
- (a) 1 点:拒绝,裸错误,未说明最少点数。**SMELL**。
- (b) 2 点:成功,预测 106、区间 [102.16,109.84]、holdout:0 且指标 null、confidence=low、warning "Series has limited history..."。**PASS**(处理最好的一例)。
- (c) 常数序列:成功,预测全 100、区间 [100,100],无除零无 NaN。**PASS**(零宽区间见 P2)。
- (d) 乱序日期:结果与正序完全一致(内部正确排序),静默无提示。**PASS**。
- (e) 重复日期不同值:拒绝,裸错误无诊断。**SMELL**。
- (f) horizon=0:拒绝(schema 层),裸文本无细节。**PASS**(归入裸错误 P2)。
- (g) horizon=200:成功无上限无警告,外推至 2042-08,末值 733(算术正确),confidence 仍 high、区间全程零宽。**SMELL**。
- (h) grain=day+月度日期:校验未发现粒度不符,预测日期生成为连续日(2025-12-02/03/04),把"每月+3"标成"每日+3",结果误导。**SMELL**。
- (i) 含 0/负值+log_linear_trend:拒绝(安全,无 NaN/Inf),裸错误无"log 要求全正值"说明。**安全 PASS/报错 SMELL**。

# 附录 F chart 组报告(Q30–Q33)

约 33 次调用。看图方式:独立视觉模型对返回 URL 逐张转录核对。执行噪音:测试端曾误发重复调用(幂等无害);1 次被宿主分类器限流拦截,重试成功;视觉通道后半段故障,8 张图"生成成功、看图未完成"如实标注。

## Q30 十四种图型
- line/area/bar/horizontal_bar/pie/scatter/heatmap/histogram/boxplot 看图全对:数值、比例、顺序、颜色全部与输入一致;**中文零乱码/方框/缺字**(甲乙丙、周一~周五、城市、渠道、期初期末等密集中文)。
- funnel/waterfall(GMV桥)/pareto/table/combo:生成成功(1200x720+URL),看图未完成,不作 PASS 依据。
- heatmap SMELL:120/150/110 显示为 1.2e+02/1.5e+02/1.1e+02(默认 value_format=".2g")。
- histogram 附注:标题一次转录为"访客单价分布"(spec 为"客单价分布"),疑读图误差,其余全部吻合。
- bar 柱顶标签 5200/4800/2100/1600 顺序未重排;pie 54.7/32.6/9.5/3.2% 逐片正确,最小片标签不重叠;boxplot 两组箱体/须线/中位线齐全。

## Q31 数值正确性
- (a) bar 甲100/乙50/丙25:柱高比约 4:2:1、顺序甲乙丙、柱顶标签 100/50/25、y 轴 0 起。**PASS**。
- (b) waterfall start 100、+30/−20/+10:期初100(蓝落地)→30(绿悬浮上)→−20(红悬浮下)→10(绿悬浮上)→期末120(蓝落地),y 0~120,连接线存在。**PASS**。
- (c) pie 50/30/20:标签 50.0/30.0/20.0%,角度 180:108:72 吻合。**PASS**。

## Q32 格式与参数
- format=svg:返回 Binary content (image/svg, 28.8KB)+"(未上传 Blob,仅返回图片字节)",契约一致。行为 **PASS**(SVG 视觉态未能核验,附 SMELL)。
- dpi=72/300/不传:均成功,尺寸均 1200x720(dpi 不改像素尺寸,仅物理尺寸/相对字号)。**PASS(附注)**。
- dpi=71/301:pydantic 拒绝,完整错误(greater_than_equal/less_than_equal + 文档链接)。**PASS**。

## Q33 错误路径
- 缺 type/缺 data/缺 encoding/y 传字符串"12"/data 空数组/y 传 "NaN"/"Infinity" 字符串/未知 type "pie3d"/encoding 引用不存在列:8/8 全部被拒绝(服务端未产出图片),但报错一律 `Error executing tool chart` 无字段名/行号/实际值。数值通道校验发生在服务端 spec 契约层(字符串能到达服务端才被拒),与 dpi 参数层(有完整 Pydantic 细节)详略割裂。8 条均 **SMELL**。
- (i) 200 点 line:一次成功秒级。**PASS(性能档)**。
- 附:入参 JSON 解析失败在客户端层报 `InputValidationError: ... could not be parsed as JSON`。

# 附录 G 报告组报告(Q34–Q37)

共 13 次调用。

## Q34 全生命周期 —— FAIL(P0 阻塞)
- publish 8 次全部失败(最小中文、最小 ASCII、{"foo":1}+meta.title、完整契约形态,含 2 次同参数重试),错误逐字相同:`Error executing tool report_html_publish`,秒级确定性失败,判定与输入无关的服务端故障(根因后由协调者定位,见 P0-1)。
- get 读路径健康:funnel-analysis-20260711 完整返回存储 JSON(meta.tags、summary.overall/kpis、conclusions[].id/title/description/data_support/importance/chart_type/chart_data)。
- 覆盖更新/delete 不可测(无成功创建物);终态 list 与基线一致,无索引残留。

## Q35 校验与错误路径
- (a) 缺 meta.title、(b) 非法 id 变体(带空格/中文,均带 qa- 前缀避免不可删除脏数据)、(e) 无关字段:与宕机逐字同文本,校验路径不可达,不可评估。**FAIL(阻塞)**。
- (c) get 不存在 id:报错但无 "not found" 字样,不可操作(读路径健康前提下可确认语义为不存在)。**SMELL**。
- (d) delete 不存在 id:报错(非静默成功),裸文本,无法区分"不存在"与"故障"。**SMELL**。

## Q36 图片生成 —— PASS(一次,未重试)
- prompt:16:9 横版数据播报/深色商务/标题「8 月经营月报」/GMV ¥1,250 万环比+8.5%、新客 4,320 人、复购率 27.3%;url 格式,seed=42,size=2K。
- 返回:provider "volcengine"、model "doubao-seedream-5-0-pro-260628"、status "completed"、request_id "02178772997009553952e287ddd1b7d9109cd0048896ba053bb35"(嵌入 URL 可追溯)、usage {generated_images:1, output_tokens:17424}、images[0] 为火山 TOS 预签名直链(X-Tos-Expires=86400 与"约 24h"精确吻合)、size "2816x1584"(精确 16:9)、format jpeg。
- 备注:seed 被静默接受不回显;URL 含签名凭证,分享需整链转发并提醒 24h 时效。图片内容数字未做视觉核验。

## Q37 list 结构
- 条目 6 字段齐备(id/title/created_at/updated_at/summary/tags),summary 为存储 JSON summary.overall 的纯文本投影;排序符合最新在前(created 与 updated 降序在现有数据下不可区分);无分页参数与数量上限说明;时间戳毫秒位不统一。**PASS(部分结论受限)**。
- tags 结构性证据:get(funnel) 显示 tags 存于 meta.tags 且与索引一致(高置信,publish 宕机未能实测)。
- 清理确认:qa- 报告未入索引,三份正式报告终态完好。

# 附录 H 端到端组报告(Q38–Q42)

## Q38 异动归因+瀑布图
- 流程:diagnosing-anomalies → contribute(add) → visualizing-data → chart。
- contribute:delta=150、residual=0、自营/直播各 70(46.67%)、平台 10(6.67%),守恒成立。
- waterfall 两次调用(x/y+is_total 与 category/value/measure 两种字段命名)均零细节失败,降级 bar 成功,视觉复核读到标题与三柱数值 70/10/70 与输入一致。
- 断裂点:visualizing-data"常见失败"节承诺"ContractError 指向具体字段/行",实际为无字段指向的笼统异常;chart schema 不展开 waterfall encoding 约定,references 只在本地,纯凭描述无法构造合法 spec。
- 次要异常:chart 成功时返回两个不同 URL(image source 为 maas-log-prod.cn-wlcb.ufileos.com 签名地址,文本块声称 vercel-storage.com Blob URL),二者并存且来源未说明。
- **SMELL**(归因 PASS;瀑布图 FAIL→后由图表组证明契约正确时可渲染,定性为契约不可发现)。

## Q39 趋势预测
- 流程:predicting-trends → forecast(auto_baseline, horizon=3) → chart(line)。
- 预测 2026-01=247.35(246.61–248.09)、02=251.2、03=255.05,完美延续 +4/月;三点均落区间内;上下界随点值单调但宽度恒定(1.478)不展宽;backtest MAE=0.333、MAPE=0.1372%;auto 选 holt_linear(理由 recent holdout MAPE 0.001372),与 Skill 选型表一致;Skill 第 6 节"区间不会自动随 horizon 充分展宽"与实际精确吻合。**PASS**。

## Q40 实验评估
- 流程:evaluating-impact → impact(ab_rate)。
- control_rate=0.10、treatment_rate=0.11、absolute_lift=0.01、relative_lift=+10%、p_value=0.021075、CI=[0.001504,0.018496](不含 0);手工核算逐位一致。Skill 决策标准清晰可执行并明示边界(不自动做 SRM/污染/提前停止检查)。结论:统计显著、支持全量,但 CI 下界仅 +0.15pp,若业务最小可接受效果高于此需标注 caveat。**PASS**。

## Q41 语义→取数链路
- 流程:orchestrating-analytics + retrieving-context → retrieve_search(exact_match 命中"复购人数")→ sql_schema(逻辑表)→ retrieve_doc_read(SQL 文档)→ sql_schema(4 张物理表)。
- 指标定义/分子表达式/参与计算表 semantic.fact_user_period_lifecycle/context 信息完备;但**强行 sql_schema(逻辑表)返回 `{"columns":[]}` 零警告静默空**——不知道"实现方式=sql_query"含义的 Agent 会得出"表没结构"的错误结论,这是链路最易断的一步。
- 正确路径(Skill 预设):剥文档 token `SaQ5dDqWfox5DWxLGp5cRPSwnhg` → retrieve_doc_read 拿逻辑 SQL → 底层 6 张物理表(如 xqd_data_analysis.ads_xqd_service_after_sales_recep_details_hour_bi_all)→ sql_schema 表名直接可用,180/76/423/28 列,is_repurchase 等关键字段全部验证存在。
- 4 表结果 78,435 字符超 token 上限转存本地文件,本机无 jq 需 python 三步解析;列对象用中文键(字段名/数据类型/字段注释)。SQL 文档正文有 markdown 格式污染(`*,*order_id`、`select ** *from`)。
- **SMELL**(链路可走通,断裂点被工具静默化)。Skill 无漂移,提前精确预警全部三个坑。

## Q42 独立复核
- 流程:validating-analyses → sql_query(VALUES 构造独立算术路径,非重跑 contribute)复算 Q38 全部数字。
- 独立复算:自营 delta=70/share=0.466667、平台 10/0.066667、直播 70/0.466667、总 delta=150/相对变化 0.150000,与 contribute 逐位一致;守恒与分组完备性(500+300+200=1000、570+310+270=1150)成立。评级:可发布(caveat:源数据为用户口述,非受治理表取数)。
- 工具支撑缺口:Skill 步骤 7"检查图表与最终渲染态"无 mcp__sda__ 工具可做(chart 无回读校验),外部视觉 MCP 又快速 429(`MCP error 429: ... 您的账户已达到速率限制`),图形诚实性验证无法闭环,只能退化为数值复核。
- **PASS**(分析域复算无缺口)。
- 端到端最痛 3 问题:①waterfall 零信息报错+契约不可发现;②sql_schema 逻辑表静默空列+宽表溢出;③看图验证无工具支撑+chart 双 URL 来源不明。

# 附录 I 第二波终端组报告(T1–T2)

## T1 飞书文档覆盖与恢复 —— SMELL(主链路可用,写入污染)

调用序列:retrieve_search 命中模板(token `V6TYdWScDoms5axrSmkcM5FHn0b`)→ read 备份全文 → update 写入测试 markdown(全要素+特殊字符探针)→ read 回读核对 → update 写回备份 → read 发现标题重复(docx 标题块+写入 H1)→ update 去掉首行 H1 修正 → read 最终验证一致。伪造 token update 一次(未碰真文档)。全部 update 仅作用于该 token。

往返保真核对:一/二/三级标题、嵌套无序列表、有序列表、表格(3 列中文表头,读回为 HTML table 块)、SQL 代码块、加粗、行内代码、链接、分隔线——**结构全部保真**(代码块语言 `sql`→`SQL` 大写化漂移)。

污染证据(根因定位):写入 `"引号" & <大于> \#34; 反斜杠\ 与 \+20.96%` → 读回 `\&amp;\#34;引号\&amp;\#34; \&amp;amp; \&amp;lt;大于\&amp;gt; \#34; 反斜杠\\ 与 \+20\.96%`。~~写入路径将 ASCII 直引号/&/</> HTML 实体化后存入 docx(飞书正文实际可见 `&#34;` 等实体文本),导出 markdown 再对 `&` 加转义。**这复现并解释了第一波正文残留——是写入路径行为,不是读出路径旧数据。**~~

> **勘误(2026-08-27)**:本节"根因在写入侧"的方向判断错误。判别探针(list_blocks 直读存储)证明 docx 存储层干净,实体化只发生在 `docs/v1/content` 导出侧;上文的"双层 `\&amp;\#34;`"形态是 subagent 报告经任务通知通道转播时 `&` 被二次转义的伪影,文档真实导出为单层 `\&\#34;`(平台治理文档直读 API 验证:单层 4 处、双层 0 处、存储 0 实体字面量)。结论:无任何文档被污染入库,"读写累积"机制成立但从未发生;修复为读取侧解码,往返自此幂等。

恢复验证:标题唯一、两张表格(5×5、4×2)逐字一致(含 `\+20\.96%` 转义、↑↓箭头、✅⚠️❌ emoji)、代码块逐字一致(含行尾空格)、列表/引用/链接/首尾段全部一致。3 处不可复原差异:①空 `> ` 引用行被丢弃;②代码块语言大写化;③嵌套加粗/行内代码边界部分星号转义(`**粗体中有**\*\*`行内代码`\*\*...`),重写同样输入无法复原。

错误路径:伪造 token `Error executing tool retrieve_doc_update`,无错误码/详情,秒级快速失败。

## T2 全量 sync 与重建后复检 —— PASS

- 前置:`MATCH (n) RETURN count(n)`=211、关系 498;sync(dry_run=true) validated:true、warnings:[](fetch 与参考值逐项一致)。
- 执行 sync(dry_run=false) ×1:**分钟级单次调用内正常返回,未超时未重试**。removed_schema {constraints:10, indexes:20};nodes 与 fetch 逐项一致(211);relationships 8 类合计 498(常用维度 243、使用 96、来源于 55、包含 65、启用 26、参与 13);search_text 211;indexes 10 + fulltext 10;embed 211。
- 复检:retrieve_schema 10 标签/8 关系 ✓;count 211/498 ✓;SHOW CONSTRAINTS 10 ✓;retrieve_search("复购人数是什么口径")首条 指标/repurchase_users/exact_match ✓;模板实体仍在(token 不变)✓。
- planned vs actual:清空/约束/关系/向量索引/全文索引/embedding/节点关系 **全部一致,无缺口**。

# 附录 J 协调者复核记录

1. **publish P0 复现**:协调者以字符串 summary 与对象 summary 各调用一次 `report_html_publish`,均失败;服务器日志定位双根因(P0-1 缺陷 A/B),详见上文。
2. **枚举改写定性**:协调者两次尝试发送 `method="abc"`,实际传输均为合法值——确认改写发生在调用方(MCP 客户端/模型受 schema 枚举约束),非服务端 bug。
3. **服务器日志根因**:`ssh hermes` 拉取容器日志——
   - publish 双堆栈(见 P0-1);
   - `DataSourceError: SQL 执行失败: permission denied for schema ads_bu`(FOREIGN 表不可读真因);
   - 多次 `psycopg.OperationalError: connection to server at "127.0.0.1", port 15432 failed: server closed the connection unexpectedly` → `无法连接 Hologres（检查 VPN/白名单/凭证）`(间歇抖动根因:VPN 转发器断连);
   - `cannot execute INSERT in a read-only transaction`(只读保证服务端实证);
   - 容器状态:sda-mcp Up 4 hours、sda-vpn Up 4 hours (healthy)。
