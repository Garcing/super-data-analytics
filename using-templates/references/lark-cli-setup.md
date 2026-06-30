# lark-cli 安装与配置

feishu-briefs.js 依赖 lark-cli 来操作飞书文档。

## 安装

```bash
npm install -g @anthropic-ai/lark-cli
```

## 初始化

```bash
lark-cli config init
```

按提示输入飞书应用的 App ID 和 App Secret。

## 登录授权

```bash
lark-cli auth login
```

选择需要的权限 scope，至少包含：
- `docx:document` — 读写文档
- `drive:drive` — 管理云空间文件
- `search:docs:read` — 搜索文档

## 验证

```bash
lark-cli docs +fetch --api-version v2 --help
```

如果显示帮助信息，说明安装成功。

## 故障排除

- `lark-cli: command not found` — 确认 npm 全局安装目录在 PATH 中
- `Permission denied` — 在飞书开放平台检查应用权限和 Admin Consent
- `Auth failed` — 运行 `lark-cli auth login` 重新授权
