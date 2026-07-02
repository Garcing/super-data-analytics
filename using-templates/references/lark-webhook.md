# 飞书群自定义机器人 Webhook 消息格式

来源：https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot

请求方式：POST（HTTPS）
请求地址：`https://open.feishu.cn/open-apis/bot/v2/hook/<你的 hook_id>`
Content-Type：`application/json`

频率限制：单租户单机器人 **100 次/分钟、5 次/秒**（与普通应用不同）。建议避开整点/半点发送，否则可能触发 `11232` 限流。
请求体大小：**不能超过 20 KB**。

成功响应：

```json
{ "code": 0, "msg": "success", "data": {} }
```

> 与企微不同：飞书的文本/富文本/图片/群名片消息体把内容包在 `content` 字段里；**消息卡片（interactive）例外，直接用顶层 `card` 字段**，不要放进 `content`。

## 文本消息（text）

```json
{
  "msg_type": "text",
  "content": {
    "text": "广州今日天气：29度，大部分多云，降雨概率：60%"
  }
}
```

| 参数 | 必填 | 说明 |
|---|---|---|
| msg_type | 是 | 固定为 `text` |
| content.text | 是 | 文本内容 |

### @ 用法（写在 text 里，紧贴用户名，无空格）

```json
{
  "msg_type": "text",
  "content": {
    "text": "<at user_id=\"ou_xxxxxxx\"></at> 新更新提醒"
  }
}
```

- @ 单个用户：`user_id` 须为该群成员的 **Open ID** 或 **User ID**（外部群只能用 Open ID）
- @ 所有人：`<at user_id="all"></at>`

## 富文本消息（post）

由多个"段落"组成，每个段落是一个节点数组（一行）。节点支持 `text` / `a`（超链接）/ `at`（@）/ `img`（图片）。

```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "项目更新通知",
        "content": [
          [
            { "tag": "text", "text": "项目有更新: " },
            { "tag": "a", "text": "请查看", "href": "http://www.example.com/" },
            { "tag": "at", "user_id": "ou_18eac8********17ad4f02e8bbbb" }
          ],
          [
            { "tag": "text", "text": "另一行内容" }
          ]
        ]
      }
    }
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| content.post | 是 | 富文本对象 |
| ∟ zh_cn / en_us | 是（至少一种） | 中/英文配置，二选一或多选 |
| ∟ title | 否 | 富文本标题 |
| ∟ content | 是 | `[[节点, 节点], [节点]]`，外层数组=段（行），内层=行内节点 |

常用节点标签：

| tag | 关键字段 | 说明 |
|---|---|---|
| `text` | `text` | 纯文本 |
| `a` | `text`、`href` | 超链接 |
| `at` | `user_id`（`all`=所有人）、可选 `user_name` | @ 人 |
| `img` | `image_key` | 图片（需先上传图片接口拿 key） |

> 富文本**不支持 Markdown 语法**，排版靠拆节点 + 段落分行实现；不支持表格。

## 消息卡片（interactive）— 数据播报推荐

卡片支持 header（标题 + 颜色模板）和 body（`markdown` / `div` / `column_set` / `table` / `button` 等组件）。`schema: "2.0"` 为新版结构。

```json
{
  "msg_type": "interactive",
  "card": {
    "schema": "2.0",
    "header": {
      "title": { "tag": "plain_text", "content": "平台治理健康数据播报" },
      "template": "blue"
    },
    "body": {
      "direction": "vertical",
      "elements": [
        {
          "tag": "markdown",
          "content": "**日期**：2026-06-27\n\n**核心指标**：\n- DAU **120w**，环比 +3%\n- 健康分 **92**，达标 ✅"
        },
        {
          "tag": "note",
          "elements": [
            { "tag": "plain_text", "content": "数据来源：平台治理经营看板 · 自动播报" }
          ]
        }
      ]
    }
  }
}
```

> 卡片用顶层 `card` 字段，**不要**包进 `content`。

### 卡片 markdown 支持的语法

- **标题** `# / ## / ###`
- **加粗** `**加粗**`、*斜体* `*斜体*`、~~删除线~~ `~~删除线~~`
- **链接** `[文本](url)`
- **列表**（有序 `1.`、无序 `-`，可嵌套）
- **引用** `> 引用`
- **代码**：行内 `` `code` `` 和代码块 ` ``` `
- **强调/着色**：用 header 的 `template` 颜色做整体强调，或用 `note` / `column_set` 区块组织布局

### 卡片 header 颜色模板（template）

`blue` / `wathet`（浅蓝）/ `turquoise`（青绿）/ `green` / `yellow` / `orange` / `red` / `carmine`（绛红）/ `violet`（紫）/ `purple` / `indigo` / `grey`（默认中性）

> 数据播报做颜色强调，靠 **header.template**（标题栏底色）和分区块即可；不需要像企微那样用 `<font color>` 内联色。

### 表格怎么办

卡片 `markdown` 元素**不渲染标准 Markdown 表格语法**。要在卡片里出表格，用专门的 `table` 组件（`tag: "table"`，定义 `columns` + `rows`），或用 `column_set` 做多列对齐。表格数据量小也可退化为 markdown 列表。

## 安全设置（三选一或叠加）

| 方式 | 说明 | 失败错误码 |
|---|---|---|
| 自定义关键词 | 消息内容需含至少一个关键词（最多 10 个）。**只对 text / title 文本生效**，不过滤链接 href | `19024` Key Words Not Found |
| IP 白名单 | 仅放行白名单内 IP（最多 10 个，支持段如 `123.1.1.1/24`） | `19022` Ip Not Allowed |
| 签名校验 | 请求需带 `timestamp` + `sign`，签名校验通过才放行 | `19021` sign match fail |

### 签名校验

开启后，请求体顶层加 `timestamp`（秒，距当前不超过 1 小时）和 `sign`。算法：

```
sign = Base64( HmacSHA256( key = timestamp + "\n" + secret, message = "" ) )
```

Node.js 示例：

```js
import crypto from 'node:crypto';

function genSign(timestamp, secret) {
  const stringToSign = `${timestamp}\n${secret}`;
  return crypto.createHmac('sha256', stringToSign).update('').digest('base64');
}

// 请求体顶层带上：
// { "timestamp": "<秒级时间戳>", "sign": genSign(timestamp, secret), "msg_type": "text", "content": {...} }
```

## 消息类型对比

| 能力 | text | post（富文本） | interactive（卡片） |
|---|---|---|---|
| 标题 | ❌ | ✅（title） | ✅（header + 颜色） |
| 加粗/斜体 | ❌ | ❌ | ✅（markdown） |
| 链接 | ❌ | ✅（a 标签） | ✅（markdown 链接） |
| 列表 | ❌ | ❌ | ✅（markdown） |
| 表格 | ❌ | ❌ | ✅（table 组件，非 md 语法） |
| @ 人 | ✅ | ✅（at 标签） | ✅ |
| 颜色强调 | ❌ | ❌ | ✅（header 模板色） |
| 多区块布局 | ❌ | ❌ | ✅（column_set） |
| 拼装难度 | 低 | 中 | 高 |

**播报推荐使用 `interactive` 卡片**：标题带颜色、正文 markdown 支持加粗/列表、可用 `note` 标注数据来源、`table` 出指标表格——最契合数据播报场景。

## 播报适配要点

当通过飞书 Webhook 推送播报时：

1. **优先用 interactive 卡片**：header 放播报主题（配 `template` 颜色），body 用 `markdown` 元素承载数据，`note` 标注来源/时间。
2. **指标表格**用卡片 `table` 组件，不要用 markdown 表格语法（不渲染）。
3. **颜色强调**靠 header `template`（如告警用 `red`/`orange`，正常用 `green`），不需内联 `<font>`。
4. **@ 人**：在 markdown 里用 `<at user_id="ou_xxx"></at>`，`all` @ 全员；取 Open ID 须群成员有效。
5. **体积**：请求体 ≤ 20 KB，超长拆多条；**频率** ≤ 100 条/分钟且 ≤ 5 条/秒，避开整点/半点。
6. **开启签名校验时**，记得在请求体顶层补 `timestamp` + `sign`，否则返回 `19021`。
