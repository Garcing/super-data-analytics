# super-data-analytics MCP 服务镜像
FROM python:3.12-slim

# CJK 字体（中文图表必需）+ 基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（分层缓存）
COPY pyproject.toml ./
# 项目以 editable 安装；依赖在 pyproject 的 dependencies 声明
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir uvicorn

# 中国服务器直连 HuggingFace 不通：走 hf-mirror.com + 关 Xet（Xet cas-server 在镜像源 401）
# 否则 fastembed 预下载模型 / 运行时回源都会失败。构建期与运行期都需要这两个变量。
ENV HF_ENDPOINT=https://hf-mirror.com \
    HF_HUB_DISABLE_XET=1

# 预下载 bge-small ONNX 模型，避免运行时拉取（fastembed 首次会下载）
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5')"

# 代码
COPY sda_mcp ./sda_mcp

ENV PYTHONUNBUFFERED=1 \
    SDA_MCP_PORT=3100
EXPOSE 3100

# config.json 由 compose 卷挂载（SDA_CONFIG_PATH 指向），镜像不含密钥
CMD ["python", "-m", "sda_mcp.server"]
