"""Guardrails for deployment documentation published with the project."""

from __future__ import annotations

import unittest
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DocumentationSecurityTests(unittest.TestCase):
    def test_cloud_guides_do_not_instruct_direct_streamlit_exposure(self) -> None:
        paths = (
            PROJECT_ROOT / "阿里云部署指南.md",
            PROJECT_ROOT / "中秋节演示准备清单.md",
            PROJECT_ROOT / "快速启动指南.md",
        )
        forbidden = re.compile(
            r"(?m)^\s*(?:ssh root@|streamlit run .*--server\.address 0\.0\.0\.0|.*http://你的IP:8501|.*开放8501端口)"
        )
        for path in paths:
            content = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIsNone(forbidden.search(content))

    def test_cloud_guides_require_loopback_and_tls(self) -> None:
        cloud_guide = (PROJECT_ROOT / "阿里云部署指南.md").read_text(encoding="utf-8")
        runbook = (PROJECT_ROOT / "项目工程化" / "08-部署运维" / "部署Runbook.md").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:8501", cloud_guide)
        self.assertIn("listen 443 ssl", cloud_guide)
        self.assertIn("proxy_set_header Upgrade", runbook)
        self.assertIn("不要对公网开放 `11434` 或 `8501`", runbook)


if __name__ == "__main__":
    unittest.main()
