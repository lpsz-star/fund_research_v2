import json
import shutil
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fund_research_v2.backtest.engine import run_backtest
from fund_research_v2.cli import main
from fund_research_v2.common.config import load_config
from fund_research_v2.common.date_utils import add_months, is_available_by_month_end, iter_months, month_end
from fund_research_v2.common.workflows import fetch_failed_command, prepare_bundle, run_experiment_command, run_portfolio_command, run_universe_command
from fund_research_v2.data_ingestion.providers import DatasetSnapshot, load_cached_dataset
from fund_research_v2.data_ingestion.providers import TushareDataProvider
from fund_research_v2.data_processing.fund_type_classifier import classify_fund_type
from fund_research_v2.evaluation.factor_evaluator import evaluate_factors
from fund_research_v2.features.feature_builder import build_feature_rows
from fund_research_v2.portfolio.construction import build_portfolio
from fund_research_v2.reporting.reports import render_universe_audit_report
from fund_research_v2.universe.filters import build_universe


class PipelineTest(unittest.TestCase):
    def _base_config(self, root: Path) -> dict[str, object]:
        """构造测试默认配置，确保大多数流程测试共享同一研究口径。"""
        return {
            "as_of_date": "2026-03-01",
            "data_source": "sample",
            "lookback_months": 48,
            "local_secret_path": "configs/local.json",
            "universe": {
                "allowed_primary_types": ["主动股票", "偏股混合", "灵活配置混合"],
                "exclude_name_keywords": ["ETF", "联接", "指数", "LOF", "FOF", "QDII", "债", "货币"],
                "min_history_months": 24,
                "min_assets_cny_mn": 200.0
            },
            "ranking": {
                "candidate_count": 12,
                "factor_weights": {
                    "performance_quality": 0.45,
                    "risk_control": 0.35,
                    "stability_quality": 0.20
                }
            },
            "portfolio": {
                "portfolio_size": 4,
                "weighting_method": "equal_weight",
                "single_fund_cap": 0.3,
                "single_company_max": 1
            },
            "backtest": {
                "start_month": "2023-01",
                "end_month": "2026-02",
                "benchmark_field": "benchmark_return_1m",
                "transaction_cost_bps": 10.0
            },
            "benchmark": {
                "source": "sample",
                "default_key": "broad_equity",
                "series": {
                    "broad_equity": {
                        "ts_code": None,
                        "name": "中证800样例基准"
                    },
                    "large_cap_equity": {
                        "ts_code": None,
                        "name": "沪深300样例基准"
                    }
                },
                "primary_type_map": {
                    "主动股票": "broad_equity",
                    "偏股混合": "large_cap_equity",
                    "灵活配置混合": "broad_equity"
                }
            },
            "reporting": {
                "top_ranked_limit": 8
            },
            "tushare": {
                "fund_market": "O",
                "fund_status": "L",
                "download_enabled": False,
                "use_cached_raw": True,
                "start_date": "20180101",
                "end_date": None,
                "max_funds": 100
            },
            "paths": {
                "raw_dir": str(root / "data" / "raw"),
                "clean_dir": str(root / "outputs" / "clean"),
                "feature_dir": str(root / "outputs" / "feature"),
                "result_dir": str(root / "outputs" / "result"),
                "report_dir": str(root / "outputs" / "reports"),
                "experiment_dir": str(root / "outputs" / "experiments")
            }
        }

    def _write_config(self, root: Path, config: dict[str, object]) -> Path:
        """把测试配置写入临时目录，模拟真实 CLI / 工作流读取配置文件的方式。"""
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        return config_path

    def _scoped_output_dir(self, root: Path, data_source: str, layer: str) -> Path:
        """返回某个数据源在 outputs 下的实际隔离目录。"""
        return root / "outputs" / data_source / layer

    def _scoped_raw_dir(self, root: Path, data_source: str) -> Path:
        """返回某个数据源在 raw 层的实际缓存目录。"""
        return root / "data" / "raw" / data_source

    def test_run_experiment_writes_outputs(self) -> None:
        """验证完整实验流程会产出 clean、feature、result 和 report 各层关键文件。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_experiment_command(config_path)

        # 这里同时检查多层输出，是为了防止某一步 silently fail 但命令仍然返回成功。
        self.assertTrue((self._scoped_output_dir(root, "sample", "clean") / "fund_universe_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "clean") / "manager_assignment_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "clean") / "dropped_entities.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "clean") / "fund_type_audit.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "feature") / "fund_feature_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "fund_score_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "portfolio_target_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "portfolio_snapshot.json").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "backtest_summary.json").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "factor_evaluation.json").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "factor_evaluation.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "factor_evaluation_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "portfolio_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "ingestion_audit_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "fund_type_audit_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "fetch_diagnostics_report.md").exists())
        report_text = (self._scoped_output_dir(root, "sample", "reports") / "experiment_report.md").read_text(encoding="utf-8")
        self.assertIn("Experiment Context", report_text)
        self.assertIn("Benchmark Mapping", report_text)
        self.assertIn("Latest Ranking Snapshot", report_text)
        self.assertIn("Time Boundary Notes", report_text)
        self.assertIn("Backtest Summary", report_text)
        portfolio_report = (self._scoped_output_dir(root, "sample", "reports") / "portfolio_report.md").read_text(encoding="utf-8")
        self.assertIn("Decision Context", portfolio_report)
        self.assertIn("Benchmark Mapping", portfolio_report)
        self.assertIn("Time Boundary Notes", portfolio_report)
        self.assertIn("Selected Portfolio", portfolio_report)
        universe_audit_report = (self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("Latest Month Funnel", universe_audit_report)
        self.assertIn("Type Funnel", universe_audit_report)
        self.assertIn("Reason Counts", universe_audit_report)
        ingestion_audit_report = (self._scoped_output_dir(root, "sample", "reports") / "ingestion_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("Ingestion Funnel", ingestion_audit_report)
        self.assertIn("Dropped Entities", ingestion_audit_report)
        fund_type_report = (self._scoped_output_dir(root, "sample", "reports") / "fund_type_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("By Primary Type", fund_type_report)
        self.assertIn("Sample Rows", fund_type_report)
        fetch_report = (self._scoped_output_dir(root, "sample", "reports") / "fetch_diagnostics_report.md").read_text(encoding="utf-8")
        self.assertIn("Fetch Diagnostics Report", fetch_report)

    def test_fetch_failed_command_writes_retry_summary_and_report(self) -> None:
        """验证失败增量补抓会基于上次错误样本生成补抓摘要与报告。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["data_source"] = "tushare"
        config["tushare"]["download_enabled"] = True
        config["tushare"]["use_cached_raw"] = True
        config_path = self._write_config(root, config)
        (root / "configs").mkdir(parents=True, exist_ok=True)
        (root / "configs" / "local.json").write_text(json.dumps({"tushare_token": "dummy-token"}), encoding="utf-8")
        raw_dir = self._scoped_raw_dir(root, "tushare")
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "dataset_snapshot.json").write_text(
            json.dumps(
                {
                    "source_name": "tushare",
                    "fetch_diagnostics": {
                        "api_error_samples": [
                            {"api_name": "fund_nav", "ts_code": "000001.OF", "attempt": "1", "error": "rate limit"},
                            {"api_name": "fund_share", "ts_code": "000001.OF", "attempt": "1", "error": "rate limit"},
                            {"api_name": "fund_nav", "ts_code": "000002.OF", "attempt": "1", "error": "timeout"},
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        class FakeProvider:
            """隔离外部依赖，只验证失败份额提取与结果落盘。"""

            def __init__(self, config, token, project_root) -> None:
                self.config = config
                self.token = token
                self.project_root = project_root

            def warm_api_cache_for_ts_codes(self, ts_codes: list[str]) -> dict[str, object]:
                self.ts_codes = ts_codes
                return {
                    "runtime_seconds": 1.23,
                    "success_ts_code_count": 1,
                    "failed_ts_code_count_after_retry": 1,
                    "success_ts_codes": ["000001.OF"],
                    "failed_ts_codes_after_retry": ["000002.OF"],
                    "fetch_diagnostics": {
                        "api_call_stats": {"fund_nav": {"calls": 2, "failures": 1, "elapsed_seconds": 0.8}},
                        "api_cache_stats": {"fund_nav": {"hits": 0, "misses": 2}},
                        "api_error_samples": [{"api_name": "fund_nav", "ts_code": "000002.OF", "attempt": "1", "error": "timeout"}],
                    },
                }

        with mock.patch("fund_research_v2.data_ingestion.providers.TushareDataProvider", FakeProvider):
            fetch_failed_command(config_path)

        summary_path = self._scoped_output_dir(root, "tushare", "result") / "fetch_retry_summary.json"
        report_path = self._scoped_output_dir(root, "tushare", "reports") / "fetch_retry_report.md"
        self.assertTrue(summary_path.exists())
        self.assertTrue(report_path.exists())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["failed_ts_code_count"], 2)
        self.assertEqual(summary["success_ts_code_count"], 1)
        self.assertEqual(summary["failed_ts_codes_after_retry"], ["000002.OF"])
        report_text = report_path.read_text(encoding="utf-8")
        self.assertIn("Fetch Retry Report", report_text)
        self.assertIn("failed_ts_code_count: 2", report_text)
        self.assertIn("000002.OF", report_text)

    def test_run_portfolio_writes_outputs_without_backtest_artifacts(self) -> None:
        """验证独立组合流程不会误产出回测结果，避免命令职责边界混乱。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_portfolio_command(config_path)

        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "portfolio_target_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "portfolio_snapshot.json").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "portfolio_report.md").exists())
        self.assertFalse((self._scoped_output_dir(root, "sample", "result") / "backtest_summary.json").exists())
        report_text = (self._scoped_output_dir(root, "sample", "reports") / "portfolio_report.md").read_text(encoding="utf-8")
        self.assertIn("Top Ranked Candidates", report_text)
        self.assertIn("Time Boundary Notes", report_text)
        self.assertIn("Selected Portfolio", report_text)
        self.assertIn("High Ranked But Not Selected", report_text)

    def test_cli_dispatches_fetch_failed_command(self) -> None:
        """验证 CLI 已暴露失败增量补抓入口，避免工作流存在实现但无法调用。"""
        with mock.patch("fund_research_v2.cli.fetch_failed_command") as mocked_command:
            with mock.patch.object(sys, "argv", ["fund_research_v2", "fetch-failed", "--config", "configs/default.json"]):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        mocked_command.assert_called_once_with(Path("configs/default.json"))

    def test_run_universe_writes_audit_report(self) -> None:
        """验证只跑基金池时仍会输出可审计报告，而不是只留下裸 CSV。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_universe_command(config_path)

        audit_report = (self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("Audit Context", audit_report)
        self.assertIn("Latest Month Funnel", audit_report)
        self.assertIn("Type Funnel", audit_report)
        self.assertIn("Eligible Funds", audit_report)
        ingestion_report = (self._scoped_output_dir(root, "sample", "reports") / "ingestion_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("Ingestion Funnel", ingestion_report)

    def test_universe_filters_new_fund_and_low_assets(self) -> None:
        """验证样例数据中的小规模基金仍会被规模门槛挡住，且不再依赖独立年龄门槛。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        bundle = prepare_bundle(config_path)
        latest_month = max(str(row["month"]) for row in bundle["universe"].rows)
        latest_rows = [row for row in bundle["universe"].rows if str(row["month"]) == latest_month]
        reason_map = {str(row["entity_id"]): str(row["reason_codes"]) for row in latest_rows}

        self.assertIn("assets_below_threshold", reason_map["E007"])
        self.assertNotIn("fund_too_new", reason_map["E007"])

    def test_universe_uses_visible_month_asset_instead_of_latest_asset(self) -> None:
        """验证基金池规模门槛使用当月可见规模，而不是实体主表中的最新规模。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "AUM_SHIFT",
                    "entity_name": "规模爬升基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2024-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 600.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "AUM_SHIFT", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 150.0},
                {"entity_id": "AUM_SHIFT", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.01, "return_1m": 0.01, "assets_cny_mn": 260.0},
            ],
            benchmark_monthly=[{"month": "2026-01", "benchmark_return_1m": 0.0}, {"month": "2026-02", "benchmark_return_1m": 0.0}],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )

        universe = build_universe(config, dataset)
        row_map = {str(row["month"]): row for row in universe.rows if str(row["entity_id"]) == "AUM_SHIFT"}

        # 2026-01 仍应按 150 判定不达标，否则说明基金池偷看了未来月份规模。
        self.assertIn("assets_below_threshold", str(row_map["2026-01"]["reason_codes"]))
        self.assertEqual(float(row_map["2026-01"]["visible_assets_cny_mn"]), 150.0)
        self.assertEqual(float(row_map["2026-02"]["visible_assets_cny_mn"]), 260.0)

    def test_universe_audit_report_uses_visible_month_asset_not_latest_asset(self) -> None:
        """验证基金池审计报告用逐月可见规模解释结果，而不是用最新规模回头解释历史。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["universe"]["min_history_months"] = 1
        config["data_source"] = "sample"
        config_path = self._write_config(root, config)

        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "AUDIT",
                    "entity_name": "审计规模基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2024-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 999.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "AUDIT", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 120.0},
            ],
            benchmark_monthly=[{"month": "2026-02", "benchmark_return_1m": 0.0}],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={"source_name": "sample"},
        )
        universe = build_universe(load_config(config_path), dataset)

        render_universe_audit_report(
            self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md",
            config=load_config(config_path),
            dataset_metadata=dataset.metadata,
            entity_rows=dataset.fund_entity_master,
            universe_rows=universe.rows,
        )
        report_text = (self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md").read_text(encoding="utf-8")

        # 如果这里出现 999.0，说明报告仍在误用实体主表的最新规模字段。
        self.assertIn("visible_assets_cny_mn=120.0", report_text)
        self.assertNotIn("assets_cny_mn=999.0", report_text)

    def test_available_date_helpers_use_signal_month_end_boundary(self) -> None:
        """验证可得性判断严格以信号月月末为边界。"""
        self.assertEqual(month_end("2026-02"), "2026-02-28")
        self.assertEqual(add_months("2026-01", 1), "2026-02")
        self.assertEqual(iter_months("2026-01", "2026-03"), ["2026-01", "2026-02", "2026-03"])
        self.assertTrue(is_available_by_month_end("2026-02-28", "2026-02"))
        self.assertFalse(is_available_by_month_end("2026-03-01", "2026-02"))

    def test_universe_marks_nav_not_available_by_signal_month_end(self) -> None:
        """验证当月净值虽属于该月但月末前不可见时，会被基金池正确剔除。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "LATE",
                    "entity_name": "晚披露基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2025-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "LATE", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "LATE", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-03-05", "nav": 1.1, "return_1m": 0.1, "assets_cny_mn": 500.0},
            ],
            benchmark_monthly=[{"month": "2026-01", "benchmark_return_1m": 0.0}, {"month": "2026-02", "benchmark_return_1m": 0.0}],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )

        universe = build_universe(config, dataset)
        reason_map = {str(row["month"]): str(row["reason_codes"]) for row in universe.rows if str(row["entity_id"]) == "LATE"}

        self.assertIn("no_available_nav_for_month", reason_map["2026-02"])
        self.assertIn("insufficient_history", reason_map["2026-02"])

    def test_feature_builder_does_not_use_future_available_returns(self) -> None:
        """验证特征窗口不会偷看未来才披露的月收益。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "LOOKAHEAD",
                    "entity_name": "反前视基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2024-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "LOOKAHEAD", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "LOOKAHEAD", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.02, "return_1m": 0.02, "assets_cny_mn": 510.0},
                {"entity_id": "LOOKAHEAD", "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-04-03", "nav": 1.224, "return_1m": 0.2, "assets_cny_mn": 520.0},
            ],
            benchmark_monthly=[
                {"month": "2026-01", "benchmark_return_1m": 0.0},
                {"month": "2026-02", "benchmark_return_1m": 0.0},
                {"month": "2026-03", "benchmark_return_1m": 0.0},
            ],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "LOOKAHEAD", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "LOOKAHEAD", "month": "2026-02", "is_eligible": 1},
            {"entity_id": "LOOKAHEAD", "month": "2026-03", "is_eligible": 0},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        # 2026-03 的净值在 2026-04 才可见，因此 2026-03 不应生成特征，2026-02 的 3 个月收益也不应掺入它。
        self.assertEqual(sorted(month_map), ["2026-01", "2026-02"])
        self.assertAlmostEqual(float(month_map["2026-02"]["ret_3m"]), 0.0302, places=6)

    def test_feature_builder_does_not_use_future_available_benchmark(self) -> None:
        """验证超额收益只使用信号月月末前已可见的 benchmark 月收益。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "BENCH",
                    "entity_name": "基准时点基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2024-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "BENCH", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "BENCH", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.02, "return_1m": 0.02, "assets_cny_mn": 510.0},
            ],
            benchmark_monthly=[
                {"month": "2026-01", "benchmark_return_1m": 0.01, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_return_1m": 0.5, "available_date": "2026-03-03"},
            ],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "BENCH", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "BENCH", "month": "2026-02", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        # 2026-02 的 benchmark 直到 2026-03-03 才可见，因此 2026-02 的 excess_ret_12m 只能扣掉 2026-01 的 benchmark 收益。
        self.assertAlmostEqual(float(month_map["2026-02"]["ret_12m"]), 0.0302, places=6)
        self.assertAlmostEqual(float(month_map["2026-02"]["excess_ret_12m"]), 0.0202, places=6)

    def test_portfolio_limits_single_company_exposure(self) -> None:
        """验证组合构建会遵守单公司暴露约束且最终权重和为 1。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        bundle = prepare_bundle(config_path)
        latest_month = max(str(row["month"]) for row in bundle["score_rows"])
        latest_scores = [row for row in bundle["score_rows"] if str(row["month"]) == latest_month]

        portfolio = build_portfolio(load_config(config_path), latest_scores)

        companies = [str(row["fund_company"]) for row in portfolio]
        # 公司名去重后数量应不变，说明没有超出单公司上限。
        self.assertEqual(len(companies), len(set(companies)))
        self.assertAlmostEqual(sum(float(row["target_weight"]) for row in portfolio), 1.0, places=5)

    def test_backtest_respects_next_month_execution(self) -> None:
        """验证回测严格按“当月信号、下月执行”的时间规则运行。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        bundle = prepare_bundle(config_path)

        rows = run_backtest(load_config(config_path), bundle["score_rows"], bundle["dataset"].fund_nav_monthly, bundle["dataset"].benchmark_monthly)

        self.assertGreater(len(rows), 0)
        self.assertLess(rows[0]["signal_month"], rows[0]["execution_month"])

    def test_backtest_uses_continuous_months_and_records_empty_portfolio_months(self) -> None:
        """验证回测按完整月历推进，即使中间月份没有评分结果也会显式写出空仓期。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_payload = self._base_config(root)
        config_payload["backtest"]["start_month"] = "2026-01"
        config_payload["backtest"]["end_month"] = "2026-03"
        config = load_config(self._write_config(root, config_payload))
        score_rows = [
            {
                "entity_id": "ONLY",
                "month": "2026-01",
                "entity_name": "唯一基金",
                "fund_company": "测试基金",
                "rank": 1,
                "total_score": 1.0,
            }
        ]
        nav_rows = [
            {"entity_id": "ONLY", "month": "2026-02", "return_1m": 0.05},
            {"entity_id": "ONLY", "month": "2026-03", "return_1m": -0.02},
        ]
        benchmark_rows = [
            {"month": "2026-01", "benchmark_return_1m": 0.0},
            {"month": "2026-02", "benchmark_return_1m": 0.01},
            {"month": "2026-03", "benchmark_return_1m": 0.02},
        ]

        rows = run_backtest(config, score_rows, nav_rows, benchmark_rows)

        self.assertEqual([str(row["signal_month"]) for row in rows], ["2026-01", "2026-02"])
        self.assertEqual([str(row["execution_month"]) for row in rows], ["2026-02", "2026-03"])
        self.assertEqual(int(rows[0]["holdings"]), 1)
        # 2026-02 没有评分结果，因此 2026-02 -> 2026-03 应明确记录为空仓期，而不是被静默跳过。
        self.assertEqual(int(rows[1]["holdings"]), 0)
        # 当前组合构建会受 single_fund_cap 约束，单只基金组合默认不是满仓，因此空仓期净收益只反映卖出成本。
        self.assertEqual(float(rows[1]["portfolio_return_net"]), -0.00015)
        # 从持仓变为空仓意味着发生一次卖出，因此换手不应为 0。
        self.assertEqual(float(rows[1]["turnover"]), 0.15)

    def test_manager_tenure_uses_real_manager_start_month(self) -> None:
        """验证样例数据中的经理任期使用真实任职起始月，而不是基金成立月近似。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        bundle = prepare_bundle(config_path)
        latest_month = max(str(row["month"]) for row in bundle["feature_rows"])
        latest_rows = [row for row in bundle["feature_rows"] if str(row["month"]) == latest_month]
        tenure_map = {str(row["entity_id"]): int(row["manager_tenure_months"]) for row in latest_rows}

        self.assertEqual(tenure_map["E004"], 26)

    def test_manager_tenure_prefers_monthly_manager_assignment(self) -> None:
        """验证换经理场景下，特征层优先使用逐月经理映射计算任期。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "SHIFT",
                    "entity_name": "换经理基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "现任经理",
                    "manager_start_month": "2026-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "SHIFT", "month": "2025-12", "nav_date": "2025-12-31", "available_date": "2025-12-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "SHIFT", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.01, "return_1m": 0.01, "assets_cny_mn": 500.0},
            ],
            benchmark_monthly=[
                {"month": "2025-12", "benchmark_return_1m": 0.0},
                {"month": "2026-01", "benchmark_return_1m": 0.0},
            ],
            manager_assignment_monthly=[
                {"entity_id": "SHIFT", "month": "2025-12", "manager_name": "老经理", "manager_start_month": "2024-06", "manager_end_month": "2025-12"},
                {"entity_id": "SHIFT", "month": "2026-01", "manager_name": "现任经理", "manager_start_month": "2026-01", "manager_end_month": ""},
            ],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "SHIFT", "month": "2025-12", "is_eligible": 1},
            {"entity_id": "SHIFT", "month": "2026-01", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        # 2025-12 和 2026-01 应绑定不同经理，否则说明系统仍在把当前经理反向覆盖历史。
        self.assertEqual(month_map["2025-12"]["manager_name"], "老经理")
        self.assertEqual(int(month_map["2025-12"]["manager_tenure_months"]), 19)
        self.assertEqual(month_map["2026-01"]["manager_name"], "现任经理")
        self.assertEqual(int(month_map["2026-01"]["manager_tenure_months"]), 1)

    def test_manager_tenure_falls_back_or_clamps_on_bad_manager_start_month(self) -> None:
        """验证经理起始月异常时，任期计算会安全回退而不是出现负任期。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "FUTURE",
                    "entity_name": "未来经理基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2027-01",
                    "inception_month": "2024-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                },
                {
                    "entity_id": "MISSING",
                    "entity_name": "缺失经理基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理乙",
                    "manager_start_month": "",
                    "inception_month": "2024-06",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                },
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "FUTURE", "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-03-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "MISSING", "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-03-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
            ],
            benchmark_monthly=[{"month": "2026-03", "benchmark_return_1m": 0.0}],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "FUTURE", "month": "2026-03", "is_eligible": 1},
            {"entity_id": "MISSING", "month": "2026-03", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        tenure_map = {str(row["entity_id"]): int(row["manager_tenure_months"]) for row in rows}

        # FUTURE 应回退到成立月；MISSING 也应回退到成立月，而不是报错或得到 0。
        self.assertEqual(tenure_map["FUTURE"], 27)
        self.assertEqual(tenure_map["MISSING"], 22)

    def test_cli_fetch_uses_fetch_command(self) -> None:
        """验证 CLI 的 fetch 子命令正确路由到抓取入口。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_dir = root / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "default.json"
        config_path.write_text(json.dumps(self._base_config(root), ensure_ascii=False), encoding="utf-8")

        argv = ["fund_research_v2", "fetch", "--config", str(config_path)]
        with mock.patch("fund_research_v2.cli.fetch_command") as mocked_fetch:
            with mock.patch.object(sys, "argv", argv):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        mocked_fetch.assert_called_once()

    def test_cli_run_portfolio_uses_portfolio_command(self) -> None:
        """验证 CLI 的 run-portfolio 子命令正确路由到组合入口。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_dir = root / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "default.json"
        config_path.write_text(json.dumps(self._base_config(root), ensure_ascii=False), encoding="utf-8")

        argv = ["fund_research_v2", "run-portfolio", "--config", str(config_path)]
        with mock.patch("fund_research_v2.cli.run_portfolio_command") as mocked_portfolio:
            with mock.patch.object(sys, "argv", argv):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        mocked_portfolio.assert_called_once()

    def test_load_cached_dataset_reads_persisted_sample_snapshot(self) -> None:
        """验证 sample 数据跑完实验后，可以从 raw 层重新读回同一份快照。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["data_source"] = "sample"
        config_path = self._write_config(root, config)
        run_experiment_command(config_path)

        dataset = load_cached_dataset(load_config(config_path), root)

        self.assertIsNotNone(dataset)
        assert isinstance(dataset, DatasetSnapshot)
        self.assertGreater(len(dataset.fund_entity_master), 0)

    def test_load_cached_dataset_rejects_snapshot_from_other_data_source(self) -> None:
        """验证缓存会校验数据源与 benchmark 口径，防止 sample / tushare 串仓。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        sample_config = self._base_config(root)
        sample_config["data_source"] = "sample"
        sample_config_path = self._write_config(root, sample_config)
        run_experiment_command(sample_config_path)

        tushare_config = self._base_config(root)
        tushare_config["data_source"] = "tushare"
        tushare_config["benchmark"] = {
            "source": "tushare_index",
            "default_key": "broad_equity",
            "series": {
                "broad_equity": {
                    "ts_code": "000906.SH",
                    "name": "中证800"
                },
                "large_cap_equity": {
                    "ts_code": "000300.SH",
                    "name": "沪深300"
                }
            },
            "primary_type_map": {
                "主动股票": "broad_equity",
                "偏股混合": "large_cap_equity",
                "灵活配置混合": "broad_equity"
            }
        }
        tushare_config["tushare"]["download_enabled"] = False
        tushare_config["tushare"]["use_cached_raw"] = True
        tushare_config_path = self._write_config(root, tushare_config)

        dataset = load_cached_dataset(load_config(tushare_config_path), root)

        self.assertIsNone(dataset)

    def test_entity_assets_are_aggregated_across_share_classes(self) -> None:
        """验证实体规模按同一基金下各份额求和，而收益仍由代表份额承载。"""
        provider = object.__new__(TushareDataProvider)

        def fake_fetch_monthly_nav_rows(ts_code: str, entity_id: str) -> tuple[float, list[dict[str, object]]]:
            """构造 A/C 两类份额的月度净值与规模，用于隔离测试实体汇总逻辑。"""
            if ts_code == "A.OF":
                return 110.0, [
                    {"entity_id": entity_id, "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-03-01", "nav": 1.0, "return_1m": 0.02, "assets_cny_mn": 100.0},
                    {"entity_id": entity_id, "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-04-01", "nav": 1.02, "return_1m": 0.02, "assets_cny_mn": 110.0},
                ]
            if ts_code == "C.OF":
                return 55.0, [
                    {"entity_id": entity_id, "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-03-01", "nav": 0.99, "return_1m": 0.019, "assets_cny_mn": 50.0},
                    {"entity_id": entity_id, "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-04-01", "nav": 1.01, "return_1m": 0.02, "assets_cny_mn": 55.0},
                ]
            raise AssertionError(f"unexpected ts_code {ts_code}")

        provider._fetch_monthly_nav_rows = fake_fetch_monthly_nav_rows  # type: ignore[method-assign]
        share_class_rows = [
            {"ts_code": "A.OF", "name": "测试基金A", "status": "L", "found_date": "20200101"},
            {"ts_code": "C.OF", "name": "测试基金C", "status": "L", "found_date": "20200101"},
        ]

        latest_assets, entity_nav_rows = provider._fetch_entity_monthly_nav_rows(share_class_rows, "TEST::测试基金")

        # 最新规模和历史规模都应按份额求和，但 return_1m 仍应来自代表份额 A 的收益路径。
        self.assertEqual(latest_assets, 165.0)
        self.assertEqual(entity_nav_rows[-1]["assets_cny_mn"], 165.0)
        self.assertEqual(entity_nav_rows[0]["assets_cny_mn"], 150.0)
        self.assertEqual(entity_nav_rows[-1]["return_1m"], 0.02)

    def test_fetch_manager_df_uses_cache(self) -> None:
        """验证同一 ts_code 的经理接口只抓一次，避免在当前经理和月频映射中重复请求。"""
        provider = object.__new__(TushareDataProvider)
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        provider.project_root = root
        provider.config = type(
            "ConfigLike",
            (),
            {
                "data_source": "tushare",
                "paths": type("PathsLike", (), {"raw_dir": Path("data/raw")})(),
                "tushare": type("TushareLike", (), {"request_retry_count": 0, "request_pause_ms": 0})(),
            },
        )()
        provider._manager_df_cache = {}
        provider._monthly_nav_cache = {}
        provider._api_call_stats = defaultdict(lambda: {"calls": 0, "failures": 0, "elapsed_seconds": 0.0})
        provider._api_error_samples = []
        provider._api_last_call_at = {}
        provider._api_min_interval_seconds = {}
        provider._api_cache_hits = defaultdict(int)
        provider._api_cache_misses = defaultdict(int)
        import pandas as pd
        provider.pd = pd

        class ClientLike:
            def __init__(self) -> None:
                self.calls = 0

            def fund_manager(self, ts_code: str):
                self.calls += 1
                return pd.DataFrame([{"ts_code": ts_code}])

        provider.client = ClientLike()

        first = provider._fetch_manager_df("TEST.OF")
        second = provider._fetch_manager_df("TEST.OF")

        self.assertEqual(first.to_dict("records"), second.to_dict("records"))
        self.assertEqual(provider.client.calls, 1)

    def test_api_call_uses_persisted_disk_cache(self) -> None:
        """验证单接口响应会落到磁盘缓存，并在新 provider 实例中直接命中。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        import pandas as pd

        def build_provider() -> TushareDataProvider:
            provider = object.__new__(TushareDataProvider)
            provider.project_root = root
            provider.config = type(
                "ConfigLike",
                (),
                {
                    "data_source": "tushare",
                    "paths": type("PathsLike", (), {"raw_dir": Path("data/raw")})(),
                    "tushare": type("TushareLike", (), {"request_retry_count": 0, "request_pause_ms": 0})(),
                },
            )()
            provider._manager_df_cache = {}
            provider._monthly_nav_cache = {}
            provider._api_call_stats = defaultdict(lambda: {"calls": 0, "failures": 0, "elapsed_seconds": 0.0})
            provider._api_error_samples = []
            provider._api_last_call_at = {}
            provider._api_min_interval_seconds = {}
            provider._api_cache_hits = defaultdict(int)
            provider._api_cache_misses = defaultdict(int)
            provider.pd = pd
            return provider

        class FuncLike:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, **kwargs):
                self.calls += 1
                return pd.DataFrame([{"ts_code": kwargs["ts_code"], "value": 1}])

        first_provider = build_provider()
        first_func = FuncLike()
        first_result = first_provider._call_api("fund_manager", first_func, ts_code="TEST.OF")
        self.assertEqual(first_func.calls, 1)
        self.assertEqual(first_provider._api_cache_misses["fund_manager"], 1)

        second_provider = build_provider()
        second_func = FuncLike()
        second_result = second_provider._call_api("fund_manager", second_func, ts_code="TEST.OF")

        self.assertEqual(second_func.calls, 0)
        self.assertEqual(second_provider._api_cache_hits["fund_manager"], 1)
        self.assertEqual(first_result.to_dict("records"), second_result.to_dict("records"))

    def test_fund_type_classifier_distinguishes_active_index_and_mixed_styles(self) -> None:
        """验证基金类型标准化规则能识别主动股票、被动指数、指数增强和灵活配置混合。"""
        self.assertEqual(
            classify_fund_type(
                fund_type="普通股票型基金",
                invest_type="契约型开放式",
                fund_name="景行成长A",
                benchmark_text="沪深300收益率*80%+中债综合指数收益率*20%",
            )["primary_type"],
            "主动股票",
        )
        self.assertEqual(
            classify_fund_type(
                fund_type="股票型基金",
                invest_type="被动指数型",
                fund_name="沪深300ETF联接A",
                benchmark_text="沪深300指数收益率*95%+银行活期存款利率(税后)*5%",
            )["primary_type"],
            "被动指数",
        )
        self.assertEqual(
            classify_fund_type(
                fund_type="混合型基金",
                invest_type="指数增强型",
                fund_name="中证500指数增强A",
                benchmark_text="中证500指数收益率*95%+活期存款利率*5%",
            )["primary_type"],
            "指数增强",
        )
        self.assertEqual(
            classify_fund_type(
                fund_type="混合型基金",
                invest_type="灵活配置型",
                fund_name="灵活配置精选A",
                benchmark_text="沪深300收益率*60%+中债综合指数收益率*40%",
            )["primary_type"],
            "灵活配置混合",
        )

    def test_fund_type_classifier_marks_unknown_case_as_low_confidence_other(self) -> None:
        """验证未命中规则的基金会回退到其他，并显式标记为低置信度。"""
        result = classify_fund_type(
            fund_type="另类投资基金",
            invest_type="创新型",
            fund_name="量化对冲一号",
            benchmark_text="绝对收益目标",
        )

        self.assertEqual(result["primary_type"], "其他")
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["rule_code"], "fallback_other")

    def test_factor_evaluation_respects_factor_direction(self) -> None:
        """验证因子评估会按高值/低值方向解释下一月收益。"""
        feature_rows = [
            {"entity_id": "A", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.9, "ret_6m": 0.9, "excess_ret_12m": 0.9, "max_drawdown_12m": -0.1, "vol_12m": 0.05, "downside_vol_12m": 0.03, "manager_tenure_months": 24, "asset_stability_12m": 0.1},
            {"entity_id": "B", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.1, "ret_6m": 0.1, "excess_ret_12m": 0.1, "max_drawdown_12m": -0.3, "vol_12m": 0.2, "downside_vol_12m": 0.15, "manager_tenure_months": 6, "asset_stability_12m": 0.6},
        ]
        nav_rows = [
            {"entity_id": "A", "month": "2026-02", "return_1m": 0.04},
            {"entity_id": "B", "month": "2026-02", "return_1m": -0.02},
        ]

        result = evaluate_factors(feature_rows, nav_rows)
        row_map = {str(row["factor_name"]): row for row in result["factor_rows"]}

        self.assertEqual(int(row_map["ret_12m"]["direction_ok"]), 1)
        self.assertEqual(int(row_map["vol_12m"]["direction_ok"]), 1)
        self.assertGreater(float(row_map["ret_12m"]["avg_rankic"]), 0.0)
        self.assertGreater(float(row_map["vol_12m"]["avg_rankic"]), 0.0)

    def test_factor_evaluation_skips_months_without_next_return(self) -> None:
        """验证缺少下一月收益时，因子评估会安全跳过该月而不是报错。"""
        feature_rows = [
            {"entity_id": "A", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.2, "ret_6m": 0.2, "excess_ret_12m": 0.2, "max_drawdown_12m": -0.1, "vol_12m": 0.1, "downside_vol_12m": 0.08, "manager_tenure_months": 12, "asset_stability_12m": 0.2},
            {"entity_id": "B", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.1, "ret_6m": 0.1, "excess_ret_12m": 0.1, "max_drawdown_12m": -0.2, "vol_12m": 0.2, "downside_vol_12m": 0.15, "manager_tenure_months": 8, "asset_stability_12m": 0.3},
        ]
        nav_rows: list[dict[str, object]] = []

        result = evaluate_factors(feature_rows, nav_rows)

        self.assertEqual(int(result["summary"]["factor_count"]), 8)
        self.assertTrue(all(int(row["evaluation_months"]) == 0 for row in result["factor_rows"]))

    def test_feature_builder_uses_type_mapped_benchmark(self) -> None:
        """验证不同 primary_type 会映射到不同 benchmark 序列，而不是统一扣同一条市场基准。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = load_config(self._write_config(root, self._base_config(root)))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "EQ",
                    "entity_name": "股票基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2024-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                },
                {
                    "entity_id": "MIX",
                    "entity_name": "混合基金",
                    "primary_type": "偏股混合",
                    "fund_company": "测试基金",
                    "manager_name": "经理乙",
                    "manager_start_month": "2024-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                },
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "EQ", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "EQ", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.03, "return_1m": 0.02, "assets_cny_mn": 500.0},
                {"entity_id": "MIX", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "MIX", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.03, "return_1m": 0.02, "assets_cny_mn": 500.0},
            ],
            benchmark_monthly=[
                {"month": "2026-01", "benchmark_key": "broad_equity", "benchmark_return_1m": 0.01, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_key": "broad_equity", "benchmark_return_1m": 0.03, "available_date": "2026-02-28"},
                {"month": "2026-01", "benchmark_key": "large_cap_equity", "benchmark_return_1m": 0.005, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_key": "large_cap_equity", "benchmark_return_1m": 0.01, "available_date": "2026-02-28"},
            ],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "EQ", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "EQ", "month": "2026-02", "is_eligible": 1},
            {"entity_id": "MIX", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "MIX", "month": "2026-02", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        row_map = {(str(row["entity_id"]), str(row["month"])): row for row in rows}

        self.assertEqual(row_map[("EQ", "2026-02")]["benchmark_key"], "broad_equity")
        self.assertEqual(row_map[("MIX", "2026-02")]["benchmark_key"], "large_cap_equity")
        self.assertAlmostEqual(float(row_map[("EQ", "2026-02")]["excess_ret_12m"]), -0.0101, places=6)
        self.assertAlmostEqual(float(row_map[("MIX", "2026-02")]["excess_ret_12m"]), 0.01515, places=6)

    def test_backtest_uses_weighted_type_mapped_benchmark(self) -> None:
        """验证回测基准收益会按组合内基金类型权重聚合，而不是固定使用单一指数。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_payload = self._base_config(root)
        config_payload["backtest"]["start_month"] = "2026-01"
        config_payload["backtest"]["end_month"] = "2026-02"
        config_payload["portfolio"]["portfolio_size"] = 2
        config_payload["portfolio"]["single_fund_cap"] = 0.5
        config = load_config(self._write_config(root, config_payload))
        score_rows = [
            {
                "entity_id": "EQ",
                "month": "2026-01",
                "entity_name": "股票基金",
                "fund_company": "甲公司",
                "primary_type": "主动股票",
                "rank": 1,
                "total_score": 1.0,
            },
            {
                "entity_id": "MIX",
                "month": "2026-01",
                "entity_name": "混合基金",
                "fund_company": "乙公司",
                "primary_type": "偏股混合",
                "rank": 2,
                "total_score": 0.9,
            },
        ]
        nav_rows = [
            {"entity_id": "EQ", "month": "2026-02", "return_1m": 0.05},
            {"entity_id": "MIX", "month": "2026-02", "return_1m": 0.03},
        ]
        benchmark_rows = [
            {"month": "2026-02", "benchmark_key": "broad_equity", "benchmark_return_1m": 0.02},
            {"month": "2026-02", "benchmark_key": "large_cap_equity", "benchmark_return_1m": 0.01},
        ]

        rows = run_backtest(config, score_rows, nav_rows, benchmark_rows)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["benchmark_mix"], "broad_equity:0.5|large_cap_equity:0.5")
        self.assertAlmostEqual(float(rows[0]["benchmark_return"]), 0.015, places=6)


if __name__ == "__main__":
    unittest.main()
