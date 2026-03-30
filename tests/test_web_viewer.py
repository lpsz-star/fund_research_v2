import shutil
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fund_research_v2.cli import main
from fund_research_v2.common.workflows import run_experiment_command
from fund_research_v2.web.viewer import build_backtest_curve_rows, create_web_app
from tests.pipeline_base import PipelineTestBase


class WebViewerTest(PipelineTestBase):
    """只读网站的入口与页面回归测试。"""

    def _invoke_app(self, app, path: str, query_string: str = "") -> tuple[str, str]:
        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": "GET",
                    "PATH_INFO": path,
                    "QUERY_STRING": query_string,
                },
                start_response,
            )
        ).decode("utf-8")
        return str(captured["status"]), body

    def test_cli_dispatches_serve_web_command(self) -> None:
        """验证 CLI 已暴露本地网站入口。"""
        with mock.patch("fund_research_v2.cli.serve_web_command") as mocked_command:
            with mock.patch.object(
                sys,
                "argv",
                ["fund_research_v2", "serve-web", "--config", "configs/default.json", "--host", "0.0.0.0", "--port", "8123"],
            ):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        mocked_command.assert_called_once_with(Path("configs/default.json"), host="0.0.0.0", port=8123)

    def test_web_viewer_renders_pages_from_sample_outputs(self) -> None:
        """验证 sample 完整实验产物可以被网站正确读取并渲染。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-web-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        run_experiment_command(config_path)
        app = create_web_app(config_path)

        overview_status, overview_body = self._invoke_app(app, "/")
        backtest_status, backtest_body = self._invoke_app(app, "/backtest")
        portfolio_status, portfolio_body = self._invoke_app(app, "/portfolio")
        reports_status, reports_body = self._invoke_app(app, "/reports")

        self.assertEqual(overview_status, "200 OK")
        self.assertIn("Research Overview", overview_body)
        self.assertIn("Backtest Summary", overview_body)
        self.assertEqual(backtest_status, "200 OK")
        self.assertIn("Backtest Analysis", backtest_body)
        self.assertIn("Monthly Returns", backtest_body)
        self.assertIn("Cumulative Curve", backtest_body)
        self.assertEqual(portfolio_status, "200 OK")
        self.assertIn("Latest Portfolio Snapshot", portfolio_body)
        self.assertIn("Selected Portfolio", portfolio_body)
        self.assertEqual(reports_status, "200 OK")
        self.assertIn("Markdown Reports", reports_body)
        self.assertIn("reports / backtest_report.md", reports_body)

    def test_web_viewer_handles_missing_outputs(self) -> None:
        """验证在尚未生成回测和组合产物时，页面会给出明确提示而不是崩溃。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-web-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        app = create_web_app(config_path)

        backtest_status, backtest_body = self._invoke_app(app, "/backtest")
        portfolio_status, portfolio_body = self._invoke_app(app, "/portfolio")

        self.assertEqual(backtest_status, "200 OK")
        self.assertIn("Backtest unavailable", backtest_body)
        self.assertIn("make backtest-sample", backtest_body)
        self.assertEqual(portfolio_status, "200 OK")
        self.assertIn("Portfolio unavailable", portfolio_body)
        self.assertIn("make portfolio-sample", portfolio_body)

    def test_build_backtest_curve_rows_compounds_returns(self) -> None:
        """验证累计曲线只基于现有月度收益做只读累乘。"""
        rows = [
            {"execution_month": "2026-01", "portfolio_return_net": "0.10", "benchmark_return": "0.05"},
            {"execution_month": "2026-02", "portfolio_return_net": "-0.05", "benchmark_return": "0.02"},
        ]

        curve_rows = build_backtest_curve_rows(rows)

        self.assertEqual(curve_rows[0]["execution_month"], "2026-01")
        self.assertAlmostEqual(curve_rows[0]["portfolio_cumulative"], 0.10)
        self.assertAlmostEqual(curve_rows[0]["benchmark_cumulative"], 0.05)
        self.assertAlmostEqual(curve_rows[1]["portfolio_cumulative"], 0.045)
        self.assertAlmostEqual(curve_rows[1]["benchmark_cumulative"], 0.071)
