"""building_reports 内核：HTML 报告 + 火山方舟图片生成。streamlit 已砍。"""
from sda_mcp.skills.building_reports.html_reports import (
    PublishResult, publish_report, list_reports, get_report, delete_report,
)
from sda_mcp.skills.building_reports.image_gen import (
    GeneratedImage, ImageGenerationResult, generate_image,
)

__all__ = [
    "PublishResult", "publish_report", "list_reports", "get_report", "delete_report",
    "GeneratedImage", "ImageGenerationResult", "generate_image",
]
