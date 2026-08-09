"""building_reports 内核：HTML 报告（Vercel Blob）+ 图片生成（apimart）。streamlit 已砍。"""
from sda_mcp.skills.building_reports.html_reports import (
    PublishResult, publish_report, list_reports, get_report, delete_report,
)
from sda_mcp.skills.building_reports.image_gen import (
    SubmitResult, ImageResult, ImageStatusResult, ImageGenResult,
    submit_image, get_image_status, generate_image,
)

__all__ = [
    "PublishResult", "publish_report", "list_reports", "get_report", "delete_report",
    "SubmitResult", "ImageResult", "ImageStatusResult", "ImageGenResult",
    "submit_image", "get_image_status", "generate_image",
]
