# Hermes Agent 接入（可选）

本目录不属于 SDA 标准部署链路。仅当服务器同时运行 Hermes Agent（HERMES_HOME 为 `~/.hermes`，gateway 常驻）且用户在部署时明确要求接入时才执行。所有配置属于服务器环境差异，不进本仓库 Git；本 README 只保留操作 runbook，凭证一律留在服务器。

## 接入 MCP（静态 Bearer，无需 OAuth 流程）

```bash
ssh hermes
cp -p ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-sda
TOKEN=$(grep "^SDA_MCP_TOKEN=" ~/sda-mcp/.env | cut -d= -f2-)
cat >> ~/.hermes/config.yaml <<EOF

mcp_servers:
  sda:
    url: "http://127.0.0.1:3100/mcp"
    headers:
      Authorization: "Bearer $TOKEN"
    timeout: 600        # sync 为分钟级长任务
    connect_timeout: 60
EOF
```

## 同步 skills

用符号链接指向仓库目录，`git pull` 即生效、无需手动再同步；分类描述符即仓库 `skills/DESCRIPTION.md`：

```bash
rm -rf ~/.hermes/skills/super-data-analytics
ln -s ~/sda-mcp/skills ~/.hermes/skills/super-data-analytics
```

## 验证

两步都过才算就绪（交互式 shell 中 `hermes` 命令默认已注册）：

```bash
# MCP：应显示 Connected 且 Tools discovered: 18
hermes mcp test sda
# skills：应列出 9 个 super-data-analytics 分类的 enabled local 技能
hermes skills list
```

最后由用户在 Hermes 对话里执行 `/reload-mcp`，出现 `Added: sda` 才算接入完成；工具以 `mcp_sda_` 前缀注册。

## 维护约定

skills 经符号链接实时生效，服务器 `git pull --ff-only` 即完成更新；轮换 `SDA_MCP_TOKEN` 时同步更新 config.yaml 中的 Bearer 值并重新 `/reload-mcp`。

## 服务器环境备忘（2026-09-04 实际使用中发现）

以下两项同属服务器环境差异，不进本仓库 Git（`myqcloud-public-dns.conf` 除外，见下）；重装或迁移后需按此恢复。

### 视觉模型配置（读图）

主模型 `glm-5.3` 是纯文本端点，`vision_analyze` 没有辅助视觉模型时读图报 `Error 1210: messages.content.type 参数非法，取值范围 ['text']`。在 `~/.hermes/config.yaml` 末尾新增（等效 CLI：`hermes config set auxiliary.vision.provider glmcode`、`hermes config set auxiliary.vision.model glm-5.3-flash`）：

```yaml
auxiliary:
  vision:
    provider: glmcode       # 引用 providers.glmcode 定义，自动继承其 api_key/base_url
    model: glm-5.3-flash    # 多模态视觉模型（走智谱 Coding Plan）；glm-4.6v 也实测可用
```

`auxiliary` 块里不需要、也不应该重复写 api_key；`providers.glmcode.available_models_json` 没列视觉模型名不影响按名调用（该列表只用于 `hermes model` 交互菜单）。改动必须重启网关才生效：聊天里发 `/restart`，或外部 shell 执行 `hermes gateway restart`（会话内部无法重启自身进程）。验证：发一张图片，模型能描述即通。

### myqcloud.com 分域公共 DNS（企微图片被 SSRF 防护拦截）

症状：企微发图 Hermes 收不到，gateway.log 出现 `tools.url_safety: Blocked request to cloud metadata address: ww-aibot-img-*.cos.ap-guangzhou.myqcloud.com -> 169.254.0.47`。根因：腾讯云内网 DNS 把该域族解析到 COS 内网链路本地地址，而 Hermes SSRF 防护（`tools/url_safety.py`）对 `169.254.0.0/16` 代码级无条件拦截，`security.allow_private_urls: true` 也绕不过。

修复仅让 `*.myqcloud.com` 域族走公共 DNS，其余域名（含内网 apt 源 `mirrors.tencentyun.com`）仍走内网 DNS，无副作用；对网关透明，改完不需要重启 Hermes。配置文件即本目录 [`myqcloud-public-dns.conf`](myqcloud-public-dns.conf)（同 Caddyfile 模式：仓库为真相源，部署即拷贝）：

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo cp ~/sda-mcp/deploy/hermes/myqcloud-public-dns.conf /etc/systemd/resolved.conf.d/
sudo systemctl restart systemd-resolved
resolvectl flush-caches
# 验证：应返回公网 IP（175.6.91.x 等），不再是 169.254.0.47
getent hosts ww-aibot-img-1258476243.cos.ap-guangzhou.myqcloud.com
```
