# 企微群机器人 Webhook 消息格式

来源：https://developer.work.weixin.qq.com/document/path/99110

请求方式：POST（HTTPS）
请求地址：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<你的KEY>`
Content-Type: `application/json`

频率限制：每个机器人发送的消息不超过 20 条/分钟。

## 文本消息

```json
{
    "msgtype": "text",
    "text": {
        "content": "广州今日天气：29度，大部分多云，降雨概率：60%",
        "mentioned_list": ["wangqing", "@all"],
        "mentioned_mobile_list": ["13800001111", "@all"]
    }
}
```

| 参数 | 必填 | 说明 |
|---|---|---|
| msgtype | 是 | 固定为 `text` |
| content | 是 | 文本内容，最长不超过 2048 字节，必须是 utf8 编码 |
| mentioned_list | 否 | userid 列表，@指定成员，`@all` 提醒所有人 |
| mentioned_mobile_list | 否 | 手机号列表，@对应成员，`@all` 提醒所有人 |

支持在 content 中使用 `<@userid>` 扩展语法来 @ 群成员。

## Markdown 消息

```json
{
    "msgtype": "markdown",
    "markdown": {
        "content": "实时新增用户反馈<font color=\"warning\">132例</font>，请相关同事注意。\n>类型:<font color=\"comment\">用户反馈</font>\n>普通用户反馈:<font color=\"comment\">117例</font>\n>VIP用户反馈:<font color=\"comment\">15例</font>"
    }
}
```

| 参数 | 必填 | 说明 |
|---|---|---|
| msgtype | 是 | 固定为 `markdown` |
| content | 是 | markdown 内容，最长不超过 4096 字节，必须是 utf8 编码 |

### 支持的 Markdown 语法（子集）

1. **标题**（支持 1-6 级，# 与文字间要有空格）
   ```markdown
   # 标题一
   ## 标题二
   ### 标题三
   ```

2. **加粗** — `**加粗**`

3. **链接**
   ```markdown
   [这是一个链接](https://work.weixin.qq.com/api/doc)
   ```

4. **行内代码段**（暂不支持跨行）— `` `code` ``

5. **引用** — `> 引用内容`

6. **字体颜色**（只支持 3 种内置颜色）
   ```html
   <font color="info">绿色</font>
   <font color="comment">灰色</font>
   <font color="warning">橙红色</font>
   ```

### 不支持的语法

- 表格（`| ... |` 语法不支持）
- 列表（`-` / `1.` 语法不支持）
- 代码块（` ``` ` 语法不支持）
- 图片

## Markdown V2 消息

```json
{
    "msgtype": "markdown_v2",
    "markdown_v2": {
        "content": "# 一、标题\n## 二级标题\n### 三级标题\n# 二、字体\n*斜体*\n**加粗**\n# 三、列表\n- 无序列表 1\n- 无序列表 2\n1. 有序列表 1\n2. 有序列表 2\n# 四、引用\n> 一级引用\n>>二级引用\n# 五、链接\n[这是一个链接](https://work.weixin.qq.com/api/doc)\n# 六、分割线\n---\n# 七、代码\n`行内代码`\n# 八、表格\n| 姓名 | 文化衫尺寸 | 收货地址 |\n| :----- | :----: | -------: |\n| 张三 | S | 广州 |\n| 李四 | L | 深圳 |"
    }
}
```

| 参数 | 必填 | 说明 |
|---|---|---|
| msgtype | 是 | 固定为 `markdown_v2` |
| content | 是 | markdown_v2 内容，最长不超过 4096 字节，必须是 utf8 编码 |

### 支持的语法

1. **标题**（支持 1-6 级，# 与文字间要有空格）
2. **字体**（斜体 `*斜体*`、加粗 `**加粗**`）
3. **列表**（无序 `-` 和有序 `1.` 均支持，支持嵌套）
4. **引用**（`>` 支持多级嵌套）
5. **链接** — `[文本](url)`，支持图片 `![描述](url)`
6. **分割线** — `---`
7. **代码** — 行内代码和独立代码块均支持
8. **表格** — 完整支持，含对齐（`:---` 左对齐、`:---:` 居中、`---:` 右对齐）

### 不支持的语法

- 字体颜色（`<font color="...">` 不支持）
- @群成员

### 注意事项

- 客户端 4.1.36 以下（安卓 4.1.38 以下）消息表现为纯文本，建议使用最新客户端

## Markdown V1 vs V2 对比

| 能力 | markdown（v1） | markdown_v2 |
|---|---|---|
| 标题 | ✅ | ✅ |
| 加粗 | ✅ | ✅ |
| 链接 | ✅ | ✅ |
| 行内代码 | ✅ | ✅ |
| 引用 | ✅ | ✅ |
| 字体颜色 | ✅（info/comment/warning） | ❌ |
| @群成员 | ✅ | ❌ |
| 表格 | ❌ | ✅ |
| 列表 | ❌ | ✅ |
| 代码块 | ❌ | ✅ |
| 图片 | ❌ | ✅ |
| 分割线 | ❌ | ✅ |
| 斜体 | ❌ | ✅ |

**播报推荐使用 `markdown_v2`**，因为支持表格和列表，能直接渲染数据播报中的表格。

## 播报适配要点

当通过企微 Webhook 推送播报时：

1. **优先使用 markdown_v2**：支持表格，适合数据播报场景
2. **如需颜色标注**：用 markdown（v1）+ `<font color="warning">`，但要放弃表格，改用纯文本排版
3. **长度限制**：单条消息不超过 4096 字节，超长需拆分多条
4. **频率限制**：不超过 20 条/分钟
5. **内容必须是 utf8 编码**
