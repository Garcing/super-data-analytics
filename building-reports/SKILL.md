---
name: building-reports
description: 报告生成板块，支持 Web/PDF/PPT/图片多种报告格式
metadata: 
  skill-series: super-data-analytics
  chinese-name: 构建数据报告
---

# 构建数据报告

## 概览

将分析结果转化为不同格式的数据分析报告，支持HTML/Streamlit/Image/飞书文档/飞书幻灯片

## 格式说明

| 格式 | 输入 | 输出 |
|----------|--------|------|
| HTML | Rechart组件格式数据字段的JSON | vercel 公网链接 |
| Streamlit | 每份报告一个 reports/*.py（遵循指引） | 多页 app（本地 / Community Cloud URL） |
| Image | 文本提示词（+ 可选 size/quality/model 等） | 本地图片文件 + 公网 URL |
| 飞书文档 | 按照lark-doc要求的格式 | 飞书文档 URL |
| 飞书幻灯片 | 按照lark-slides要求的格式 | 飞书幻灯片 URL |

## 参考文档

- HTML：`scripts/html/`，接口与输入格式见 `references/report_to_html.md`
- Streamlit：`scripts/streamlit/`，接口与编写规范见 `references/report_to_streamlit.md`
- Image：`scripts/image/`，接口与用法见 `references/report_to_image.md`
- 飞书文档：参考 SKILL `lark-doc` ，报告强制创建指定文件夹，具体token参考环境变量 [`.env`](.env) 中的 `DOC_FOLDER_TOKEN `
- 飞书幻灯片：参考 SKILL `lark-slides` ，报告强制创建指定文件夹，具体token参考环境变量 [`.env`](.env) 中的 `DOC_FOLDER_SLIDES `
