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
from fund_research_v2.common.date_utils import add_months, is_available_by_month_end, iter_months, latest_completed_month, month_end, month_start
from fund_research_v2.common.io_utils import read_csv
from fund_research_v2.common.workflows import analyze_robustness_command, compare_experiments_command, fetch_failed_command, prepare_bundle, run_experiment_command, run_portfolio_command, run_universe_command
from fund_research_v2.data_ingestion.providers import DatasetSnapshot, load_cached_dataset
from fund_research_v2.data_ingestion.providers import TushareDataProvider
from fund_research_v2.data_processing.fund_type_classifier import classify_fund_type
from fund_research_v2.evaluation.factor_evaluator import evaluate_factors
from fund_research_v2.evaluation.metrics import summarize_backtest
from fund_research_v2.features.feature_builder import build_feature_rows
from fund_research_v2.portfolio.construction import build_portfolio
from fund_research_v2.ranking.scoring_engine import score_funds
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
                "transaction_cost_bps": 10.0,
                "missing_return_policy": "zero_fill_legacy",
                "missing_weight_warning_threshold": 0.05
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
        self.assertTrue((self._scoped_output_dir(root, "sample", "clean") / "fund_liquidity_audit.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "feature") / "fund_feature_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "fund_score_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "portfolio_target_monthly.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "portfolio_snapshot.json").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "backtest_summary.json").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "backtest_position_audit.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "factor_evaluation.json").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "factor_evaluation.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "factor_distribution.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "factor_bucket_performance.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "result") / "factor_correlation.csv").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "factor_evaluation_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "portfolio_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "ingestion_audit_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "fund_type_audit_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "fund_liquidity_audit_report.md").exists())
        self.assertTrue((self._scoped_output_dir(root, "sample", "reports") / "fetch_diagnostics_report.md").exists())
        report_text = (self._scoped_output_dir(root, "sample", "reports") / "experiment_report.md").read_text(encoding="utf-8")
        self.assertIn("Experiment Context", report_text)
        self.assertIn("Benchmark Mapping", report_text)
        self.assertIn("- latest_month: 2026-02", report_text)
        portfolio_snapshot = json.loads((self._scoped_output_dir(root, "sample", "result") / "portfolio_snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(portfolio_snapshot["latest_month"], "2026-02")
        feature_rows = read_csv(self._scoped_output_dir(root, "sample", "feature") / "fund_feature_monthly.csv")
        score_rows = read_csv(self._scoped_output_dir(root, "sample", "result") / "fund_score_monthly.csv")
        self.assertIn("official_research_month", feature_rows[0])
        self.assertIn("research_month_status", feature_rows[0])
        self.assertIn("official_research_month", score_rows[0])
        self.assertIn("research_month_status", score_rows[0])
        score_status = {(str(row["month"]), str(row["research_month_status"])) for row in score_rows}
        self.assertIn(("2026-02", "official"), score_status)
        self.assertNotIn(("2026-02", "observation_only"), score_status)
        self.assertIn("Latest Ranking Snapshot", report_text)
        self.assertIn("Time Boundary Notes", report_text)
        self.assertIn("Backtest Summary", report_text)
        self.assertIn("Backtest Reliability", report_text)
        self.assertIn("Top Risk Months", report_text)
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
        liquidity_report = (self._scoped_output_dir(root, "sample", "reports") / "fund_liquidity_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("Restricted Funds", liquidity_report)
        fetch_report = (self._scoped_output_dir(root, "sample", "reports") / "fetch_diagnostics_report.md").read_text(encoding="utf-8")
        self.assertIn("Fetch Diagnostics Report", fetch_report)
        backtest_report = (self._scoped_output_dir(root, "sample", "reports") / "backtest_report.md").read_text(encoding="utf-8")
        self.assertIn("Data Quality Diagnostics", backtest_report)
        self.assertIn("Low Confidence Months", backtest_report)
        self.assertIn("Highest Missing Weight Months", backtest_report)
        self.assertIn("Distribution Diagnostics", (self._scoped_output_dir(root, "sample", "reports") / "factor_evaluation_report.md").read_text(encoding="utf-8"))
        self.assertIn("Bucket Diagnostics", (self._scoped_output_dir(root, "sample", "reports") / "factor_evaluation_report.md").read_text(encoding="utf-8"))
        self.assertIn("High Correlation Pairs", (self._scoped_output_dir(root, "sample", "reports") / "factor_evaluation_report.md").read_text(encoding="utf-8"))

    def test_compare_experiments_writes_diff_artifacts(self) -> None:
        """验证最近两次实验可以被结构化比较，并输出对比报告和差异文件。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        experiment_dir = self._scoped_output_dir(root, "sample", "experiments")
        experiment_dir.mkdir(parents=True, exist_ok=True)
        registry_path = experiment_dir / "experiment_registry.jsonl"
        previous = {
            "experiment_id": "exp_20260301_sample",
            "generated_at": "2026-03-20T10:00:00Z",
            "config": {"data_source": "sample", "portfolio": {"portfolio_size": 4}},
            "dataset_snapshot": {"source_name": "sample", "entity_count": 8, "share_class_count": 12, "benchmark_name": "中证800样例基准", "month_range": {"start": "2022-01", "end": "2026-03"}},
            "git_commit": "abc",
            "type_baseline": {"latest_month": "2026-03", "entity_count": 8, "latest_row_count": 8, "eligible_count": 4, "entity_type_count": {"主动股票": 3}, "latest_type_count": {"主动股票": 3}, "eligible_type_count": {"主动股票": 2}},
            "factor_evaluation_summary": {"factor_count": 8, "strong_factor_count": 2, "weak_factor_count": 4},
            "backtest_summary": {
                "months": 12,
                "cumulative_return": 0.1,
                "benchmark_cumulative_return": 0.05,
                "excess_cumulative_return": 0.05,
                "missing_month_count": 1,
                "low_confidence_month_count": 1,
                "avg_missing_weight": 0.02,
                "max_missing_weight": 0.08,
            },
            "portfolio_snapshot_summary": {"latest_month": "2026-03", "portfolio": [{"entity_id": "E1", "entity_name": "基金甲", "fund_company": "甲公司", "rank": 1, "target_weight": 0.25}]},
            "result_dir": str(self._scoped_output_dir(root, "sample", "result")),
        }
        current = {
            "experiment_id": "exp_20260301_sample",
            "generated_at": "2026-03-20T11:00:00Z",
            "config": {"data_source": "sample", "portfolio": {"portfolio_size": 6}},
            "dataset_snapshot": {"source_name": "sample", "entity_count": 10, "share_class_count": 14, "benchmark_name": "中证800样例基准", "month_range": {"start": "2022-01", "end": "2026-03"}},
            "git_commit": "def",
            "type_baseline": {"latest_month": "2026-03", "entity_count": 10, "latest_row_count": 10, "eligible_count": 5, "entity_type_count": {"主动股票": 4}, "latest_type_count": {"主动股票": 4}, "eligible_type_count": {"主动股票": 3}},
            "factor_evaluation_summary": {"factor_count": 8, "strong_factor_count": 3, "weak_factor_count": 3},
            "backtest_summary": {
                "months": 12,
                "cumulative_return": 0.13,
                "benchmark_cumulative_return": 0.04,
                "excess_cumulative_return": 0.09,
                "missing_month_count": 3,
                "low_confidence_month_count": 2,
                "avg_missing_weight": 0.05,
                "max_missing_weight": 0.2,
            },
            "portfolio_snapshot_summary": {"latest_month": "2026-03", "portfolio": [{"entity_id": "E2", "entity_name": "基金乙", "fund_company": "乙公司", "rank": 1, "target_weight": 0.3}]},
            "result_dir": str(self._scoped_output_dir(root, "sample", "result")),
        }
        registry_path.write_text("\n".join([json.dumps(previous, ensure_ascii=False), json.dumps(current, ensure_ascii=False)]) + "\n", encoding="utf-8")

        compare_experiments_command(config_path)

        result_dir = self._scoped_output_dir(root, "sample", "result")
        report_dir = self._scoped_output_dir(root, "sample", "reports")
        self.assertTrue((result_dir / "comparison_summary.json").exists())
        self.assertTrue((result_dir / "backtest_summary_diff.json").exists())
        self.assertTrue((result_dir / "type_baseline_diff.json").exists())
        self.assertTrue((result_dir / "portfolio_diff.csv").exists())
        self.assertTrue((report_dir / "comparison_report.md").exists())
        report_text = (report_dir / "comparison_report.md").read_text(encoding="utf-8")
        self.assertIn("Comparison Report", report_text)
        self.assertIn("Config Diff", report_text)
        self.assertIn("Portfolio Diff", report_text)
        self.assertIn("Backtest Reliability Diff", report_text)
        diff_payload = json.loads((result_dir / "backtest_summary_diff.json").read_text(encoding="utf-8"))
        self.assertEqual(diff_payload["cumulative_return"]["delta"], 0.03)
        self.assertEqual(diff_payload["max_missing_weight"]["delta"], 0.12)

    def test_cli_dispatches_compare_experiments_command(self) -> None:
        """验证 CLI 已暴露实验对比入口，避免对比能力只能通过内部函数调用。"""
        with mock.patch("fund_research_v2.cli.compare_experiments_command") as mocked_command:
            with mock.patch.object(sys, "argv", ["fund_research_v2", "compare-experiments", "--config", "configs/default.json"]):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        mocked_command.assert_called_once_with(Path("configs/default.json"))

    def test_cli_dispatches_analyze_robustness_command(self) -> None:
        """验证 CLI 已暴露稳健性分析入口。"""
        with mock.patch("fund_research_v2.cli.analyze_robustness_command") as mocked_command:
            with mock.patch.object(sys, "argv", ["fund_research_v2", "analyze-robustness", "--config", "configs/tushare_scoring_v2.json"]):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        mocked_command.assert_called_once_with(Path("configs/tushare_scoring_v2.json"))

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

    def test_analyze_robustness_writes_outputs(self) -> None:
        """验证稳健性验证命令会单独产出分析文件与报告。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        baseline_config = self._base_config(root)
        candidate_config = self._base_config(root)
        candidate_config["ranking"]["category_factors"] = {
            "performance_quality": {"excess_ret_12m": 0.7, "ret_12m": 0.3},
            "risk_control": {"downside_vol_12m": 0.55, "worst_3m_avg_return_12m": 0.45},
            "stability_quality": {"asset_stability_12m": 0.7, "manager_post_change_excess_delta_12m": 0.3},
        }
        (root / "configs").mkdir(parents=True, exist_ok=True)
        baseline_path = root / "configs" / "sample.json"
        baseline_path.write_text(json.dumps(baseline_config, ensure_ascii=False, indent=2), encoding="utf-8")
        candidate_path = root / "configs" / "sample_scoring_v2.json"
        candidate_path.write_text(json.dumps(candidate_config, ensure_ascii=False, indent=2), encoding="utf-8")

        analyze_robustness_command(candidate_path)

        result_dir = self._scoped_output_dir(root, "sample", "result")
        report_dir = self._scoped_output_dir(root, "sample", "reports")
        self.assertTrue((result_dir / "robustness_summary.json").exists())
        self.assertTrue((result_dir / "robustness_time_slices.csv").exists())
        self.assertTrue((result_dir / "robustness_month_contribution.csv").exists())
        self.assertTrue((result_dir / "robustness_portfolio_behavior.csv").exists())
        self.assertTrue((result_dir / "robustness_factor_regime.csv").exists())
        self.assertTrue((report_dir / "robustness_report.md").exists())
        summary = json.loads((result_dir / "robustness_summary.json").read_text(encoding="utf-8"))
        self.assertIn("overall_assessment", summary)
        report_text = (report_dir / "robustness_report.md").read_text(encoding="utf-8")
        self.assertIn("Robustness Report", report_text)

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

    def test_universe_filters_holding_period_restricted_fund(self) -> None:
        """验证最低持有期基金会因流动性要求被基金池直接排除。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        bundle = prepare_bundle(config_path)
        latest_month = max(str(row["month"]) for row in bundle["universe"].rows)
        latest_rows = [row for row in bundle["universe"].rows if str(row["month"]) == latest_month]
        reason_map = {str(row["entity_id"]): str(row["reason_codes"]) for row in latest_rows}

        self.assertIn("holding_period_restricted", reason_map["E006"])

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
        config["as_of_date"] = "2026-04-01"
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

    def test_universe_audit_report_excludes_entities_missing_latest_month_rows_from_funnel(self) -> None:
        """验证漏斗后半段不会把缺少最新月记录的基金误算成通过历史和规模门槛。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["as_of_date"] = "2026-04-01"
        config["universe"]["min_history_months"] = 1
        config["data_source"] = "sample"
        config_path = self._write_config(root, config)

        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "KEEP",
                    "entity_name": "可投基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理甲",
                    "manager_start_month": "2024-01",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                },
                {
                    "entity_id": "MISSING",
                    "entity_name": "缺月基金",
                    "primary_type": "主动股票",
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
                {"entity_id": "KEEP", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "KEEP", "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-03-31", "nav": 1.01, "return_1m": 0.01, "assets_cny_mn": 510.0},
                {"entity_id": "MISSING", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.0, "return_1m": 0.0, "assets_cny_mn": 500.0},
            ],
            benchmark_monthly=[
                {"month": "2026-02", "benchmark_return_1m": 0.0},
                {"month": "2026-03", "benchmark_return_1m": 0.0},
            ],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={"source_name": "sample"},
        )
        universe = build_universe(load_config(config_path), dataset)

        report_path = self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md"
        render_universe_audit_report(
            report_path,
            config=load_config(config_path),
            dataset_metadata=dataset.metadata,
            entity_rows=dataset.fund_entity_master,
            universe_rows=universe.rows,
        )
        report_text = report_path.read_text(encoding="utf-8")

        self.assertIn("- eligible_count: 1", report_text)
        self.assertIn("- 满足最少历史月数后: count=1 dropped=1", report_text)
        self.assertIn("- 满足规模门槛后: count=1 dropped=0", report_text)

    def test_reports_use_latest_completed_month_instead_of_incomplete_current_month(self) -> None:
        """验证正式报告不会把尚未走完的当月误当成最新正式信号月。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_experiment_command(config_path)

        experiment_report = (self._scoped_output_dir(root, "sample", "reports") / "experiment_report.md").read_text(encoding="utf-8")
        portfolio_report = (self._scoped_output_dir(root, "sample", "reports") / "portfolio_report.md").read_text(encoding="utf-8")
        universe_report = (self._scoped_output_dir(root, "sample", "reports") / "universe_audit_report.md").read_text(encoding="utf-8")
        portfolio_snapshot = json.loads((self._scoped_output_dir(root, "sample", "result") / "portfolio_snapshot.json").read_text(encoding="utf-8"))

        self.assertIn("- latest_month: 2026-02", experiment_report)
        self.assertIn("- latest_month: 2026-02", portfolio_report)
        self.assertIn("- latest_month: 2026-02", universe_report)
        self.assertEqual(portfolio_snapshot["latest_month"], "2026-02")

    def test_monthly_outputs_mark_incomplete_month_as_observation_only(self) -> None:
        """验证结果层会把未完整月显式标记为 observation_only。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_experiment_command(config_path)

        score_rows = read_csv(self._scoped_output_dir(root, "sample", "result") / "fund_score_monthly.csv")
        feature_rows = read_csv(self._scoped_output_dir(root, "sample", "feature") / "fund_feature_monthly.csv")
        self.assertTrue(all(str(row["research_month_status"]) == "official" for row in score_rows))
        self.assertTrue(all(str(row["research_month_status"]) in {"official", "observation_only"} for row in feature_rows))

    def test_available_date_helpers_use_signal_month_end_boundary(self) -> None:
        """验证可得性判断严格以信号月月末为边界。"""
        self.assertEqual(month_end("2026-02"), "2026-02-28")
        self.assertEqual(month_start("2026-02"), "2026-02-01")
        self.assertEqual(latest_completed_month("2026-03-21"), "2026-02")
        self.assertEqual(latest_completed_month("2026-03-31"), "2026-03")
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

    def test_feature_builder_computes_drawdown_recovery_features(self) -> None:
        """验证回撤恢复度和距低点月数只基于当月可见净值路径计算。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "RECOVER",
                    "entity_name": "修复基金",
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
                {"entity_id": "RECOVER", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.0, "return_1m": 0.0, "assets_cny_mn": 500.0},
                {"entity_id": "RECOVER", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 0.8, "return_1m": -0.2, "assets_cny_mn": 480.0},
                {"entity_id": "RECOVER", "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-03-31", "nav": 0.9, "return_1m": 0.125, "assets_cny_mn": 490.0},
            ],
            benchmark_monthly=[
                {"month": "2026-01", "benchmark_return_1m": 0.0, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_return_1m": 0.0, "available_date": "2026-02-28"},
                {"month": "2026-03", "benchmark_return_1m": 0.0, "available_date": "2026-03-31"},
            ],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "RECOVER", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "RECOVER", "month": "2026-02", "is_eligible": 1},
            {"entity_id": "RECOVER", "month": "2026-03", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        self.assertAlmostEqual(float(month_map["2026-03"]["drawdown_recovery_ratio_12m"]), 0.5, places=6)
        self.assertEqual(int(month_map["2026-03"]["months_since_drawdown_low_12m"]), 1)

    def test_feature_builder_computes_return_stability_features(self) -> None:
        """验证收益稳定性因子能正确统计正收益占比与盈亏比。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "STABLE",
                    "entity_name": "稳定基金",
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
                {"entity_id": "STABLE", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.10, "return_1m": 0.10, "assets_cny_mn": 500.0},
                {"entity_id": "STABLE", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.045, "return_1m": -0.05, "assets_cny_mn": 490.0},
                {"entity_id": "STABLE", "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-03-31", "nav": 1.1495, "return_1m": 0.10, "assets_cny_mn": 510.0},
            ],
            benchmark_monthly=[
                {"month": "2026-01", "benchmark_return_1m": 0.0, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_return_1m": 0.0, "available_date": "2026-02-28"},
                {"month": "2026-03", "benchmark_return_1m": 0.0, "available_date": "2026-03-31"},
            ],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "STABLE", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "STABLE", "month": "2026-02", "is_eligible": 1},
            {"entity_id": "STABLE", "month": "2026-03", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        self.assertAlmostEqual(float(month_map["2026-03"]["hit_rate_12m"]), 0.666667, places=6)
        self.assertAlmostEqual(float(month_map["2026-03"]["profit_loss_ratio_12m"]), 2.0, places=6)
        self.assertAlmostEqual(float(month_map["2026-03"]["worst_3m_avg_return_12m"]), 0.05, places=6)

    def test_feature_builder_computes_observation_layer_candidate_factors(self) -> None:
        """验证观察层候选因子能按月频窗口正确生成，不进入评分也可稳定评估。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "OBS",
                    "entity_name": "观察基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理乙",
                    "manager_start_month": "2025-02",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 300.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "OBS", "month": "2025-08", "nav_date": "2025-08-31", "available_date": "2025-08-31", "nav": 1.0, "return_1m": 0.02, "assets_cny_mn": 100.0},
                {"entity_id": "OBS", "month": "2025-09", "nav_date": "2025-09-30", "available_date": "2025-09-30", "nav": 0.99, "return_1m": -0.01, "assets_cny_mn": 110.0},
                {"entity_id": "OBS", "month": "2025-10", "nav_date": "2025-10-31", "available_date": "2025-10-31", "nav": 1.0197, "return_1m": 0.03, "assets_cny_mn": 120.0},
                {"entity_id": "OBS", "month": "2025-11", "nav_date": "2025-11-30", "available_date": "2025-11-30", "nav": 0.968715, "return_1m": -0.05, "assets_cny_mn": 130.0},
                {"entity_id": "OBS", "month": "2025-12", "nav_date": "2025-12-31", "available_date": "2025-12-31", "nav": 0.978402, "return_1m": 0.01, "assets_cny_mn": 140.0},
                {"entity_id": "OBS", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 0.99897, "return_1m": 0.021021, "assets_cny_mn": 150.0},
                {"entity_id": "OBS", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.018949, "return_1m": 0.02, "assets_cny_mn": 160.0},
            ],
            benchmark_monthly=[
                {"month": "2025-08", "benchmark_return_1m": 0.01, "available_date": "2025-08-31"},
                {"month": "2025-09", "benchmark_return_1m": -0.02, "available_date": "2025-09-30"},
                {"month": "2025-10", "benchmark_return_1m": 0.01, "available_date": "2025-10-31"},
                {"month": "2025-11", "benchmark_return_1m": -0.03, "available_date": "2025-11-30"},
                {"month": "2025-12", "benchmark_return_1m": 0.0, "available_date": "2025-12-31"},
                {"month": "2026-01", "benchmark_return_1m": 0.01, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_return_1m": 0.03, "available_date": "2026-02-28"},
            ],
            manager_assignment_monthly=[
                {"entity_id": "OBS", "month": "2025-08", "manager_name": "经理甲", "manager_start_month": "2025-01", "manager_end_month": "2025-09"},
                {"entity_id": "OBS", "month": "2025-09", "manager_name": "经理甲", "manager_start_month": "2025-01", "manager_end_month": "2025-09"},
                {"entity_id": "OBS", "month": "2025-10", "manager_name": "经理乙", "manager_start_month": "2025-10", "manager_end_month": ""},
                {"entity_id": "OBS", "month": "2025-11", "manager_name": "经理乙", "manager_start_month": "2025-10", "manager_end_month": ""},
                {"entity_id": "OBS", "month": "2025-12", "manager_name": "经理乙", "manager_start_month": "2025-10", "manager_end_month": ""},
                {"entity_id": "OBS", "month": "2026-01", "manager_name": "经理丙", "manager_start_month": "2026-01", "manager_end_month": ""},
                {"entity_id": "OBS", "month": "2026-02", "manager_name": "经理丙", "manager_start_month": "2026-01", "manager_end_month": ""},
            ],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "OBS", "month": "2025-08", "is_eligible": 1},
            {"entity_id": "OBS", "month": "2025-09", "is_eligible": 1},
            {"entity_id": "OBS", "month": "2025-10", "is_eligible": 1},
            {"entity_id": "OBS", "month": "2025-11", "is_eligible": 1},
            {"entity_id": "OBS", "month": "2025-12", "is_eligible": 1},
            {"entity_id": "OBS", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "OBS", "month": "2026-02", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        self.assertAlmostEqual(float(month_map["2026-02"]["excess_hit_rate_12m"]), 0.714286, places=6)
        self.assertAlmostEqual(float(month_map["2026-02"]["tail_loss_ratio_12m"]), 1.0, places=6)
        self.assertEqual(int(month_map["2026-02"]["manager_change_count_24m"]), 2)
        self.assertAlmostEqual(float(month_map["2026-02"]["asset_growth_6m"]), 0.6, places=6)

    def test_feature_builder_computes_second_batch_observation_factors(self) -> None:
        """验证第二批观察层候选因子能正确反映路径连续性、回撤拖延、换帅后下行变化与资金流波动。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "OBS2",
                    "entity_name": "观察基金二号",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "经理丙",
                    "manager_start_month": "2025-12",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 177.1561,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "OBS2", "month": "2025-08", "nav_date": "2025-08-31", "available_date": "2025-08-31", "nav": 1.04, "return_1m": 0.04, "assets_cny_mn": 100.0},
                {"entity_id": "OBS2", "month": "2025-09", "nav_date": "2025-09-30", "available_date": "2025-09-30", "nav": 1.0712, "return_1m": 0.03, "assets_cny_mn": 110.0},
                {"entity_id": "OBS2", "month": "2025-10", "nav_date": "2025-10-31", "available_date": "2025-10-31", "nav": 1.092624, "return_1m": 0.02, "assets_cny_mn": 121.0},
                {"entity_id": "OBS2", "month": "2025-11", "nav_date": "2025-11-30", "available_date": "2025-11-30", "nav": 1.048919, "return_1m": -0.04, "assets_cny_mn": 133.1},
                {"entity_id": "OBS2", "month": "2025-12", "nav_date": "2025-12-31", "available_date": "2025-12-31", "nav": 1.027941, "return_1m": -0.02, "assets_cny_mn": 146.41},
                {"entity_id": "OBS2", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 1.03822, "return_1m": 0.01, "assets_cny_mn": 161.051},
                {"entity_id": "OBS2", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 1.058984, "return_1m": 0.02, "assets_cny_mn": 177.1561},
            ],
            benchmark_monthly=[
                {"month": "2025-08", "benchmark_return_1m": 0.01, "available_date": "2025-08-31"},
                {"month": "2025-09", "benchmark_return_1m": 0.0, "available_date": "2025-09-30"},
                {"month": "2025-10", "benchmark_return_1m": 0.01, "available_date": "2025-10-31"},
                {"month": "2025-11", "benchmark_return_1m": -0.01, "available_date": "2025-11-30"},
                {"month": "2025-12", "benchmark_return_1m": 0.0, "available_date": "2025-12-31"},
                {"month": "2026-01", "benchmark_return_1m": 0.0, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_return_1m": 0.01, "available_date": "2026-02-28"},
            ],
            manager_assignment_monthly=[
                {"entity_id": "OBS2", "month": "2025-08", "manager_name": "经理甲", "manager_start_month": "2025-01", "manager_end_month": "2025-09"},
                {"entity_id": "OBS2", "month": "2025-09", "manager_name": "经理甲", "manager_start_month": "2025-01", "manager_end_month": "2025-09"},
                {"entity_id": "OBS2", "month": "2025-10", "manager_name": "经理乙", "manager_start_month": "2025-10", "manager_end_month": "2025-11"},
                {"entity_id": "OBS2", "month": "2025-11", "manager_name": "经理乙", "manager_start_month": "2025-10", "manager_end_month": "2025-11"},
                {"entity_id": "OBS2", "month": "2025-12", "manager_name": "经理丙", "manager_start_month": "2025-12", "manager_end_month": ""},
                {"entity_id": "OBS2", "month": "2026-01", "manager_name": "经理丙", "manager_start_month": "2025-12", "manager_end_month": ""},
                {"entity_id": "OBS2", "month": "2026-02", "manager_name": "经理丙", "manager_start_month": "2025-12", "manager_end_month": ""},
            ],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "OBS2", "month": "2025-08", "is_eligible": 1},
            {"entity_id": "OBS2", "month": "2025-09", "is_eligible": 1},
            {"entity_id": "OBS2", "month": "2025-10", "is_eligible": 1},
            {"entity_id": "OBS2", "month": "2025-11", "is_eligible": 1},
            {"entity_id": "OBS2", "month": "2025-12", "is_eligible": 1},
            {"entity_id": "OBS2", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "OBS2", "month": "2026-02", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        self.assertEqual(int(month_map["2026-02"]["excess_streak_6m"]), 2)
        self.assertAlmostEqual(float(month_map["2026-02"]["drawdown_duration_ratio_12m"]), 0.571429, places=6)
        self.assertAlmostEqual(float(month_map["2026-02"]["manager_post_change_downside_vol_delta_12m"]), -0.02, places=6)
        self.assertAlmostEqual(float(month_map["2026-02"]["asset_flow_volatility_12m"]), 0.0, places=6)

    def test_feature_builder_computes_manager_post_change_excess_delta(self) -> None:
        """验证经理变更前后超额收益改善因子只比较当前经理上任前后的可见月度超额收益。"""
        config = load_config(self._write_config(Path(tempfile.mkdtemp(prefix="fund-research-v2-")), self._base_config(Path(tempfile.mkdtemp(prefix="unused-")))))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "TURN",
                    "entity_name": "换帅基金",
                    "primary_type": "主动股票",
                    "fund_company": "测试基金",
                    "manager_name": "新经理",
                    "manager_start_month": "2026-04",
                    "inception_month": "2020-01",
                    "latest_assets_cny_mn": 500.0,
                    "status": "L",
                }
            ],
            fund_share_class_map=[],
            fund_nav_monthly=[
                {"entity_id": "TURN", "month": "2026-01", "nav_date": "2026-01-31", "available_date": "2026-01-31", "nav": 0.98, "return_1m": -0.02, "assets_cny_mn": 500.0},
                {"entity_id": "TURN", "month": "2026-02", "nav_date": "2026-02-28", "available_date": "2026-02-28", "nav": 0.9604, "return_1m": -0.02, "assets_cny_mn": 500.0},
                {"entity_id": "TURN", "month": "2026-03", "nav_date": "2026-03-31", "available_date": "2026-03-31", "nav": 0.941192, "return_1m": -0.02, "assets_cny_mn": 500.0},
                {"entity_id": "TURN", "month": "2026-04", "nav_date": "2026-04-30", "available_date": "2026-04-30", "nav": 0.969428, "return_1m": 0.03, "assets_cny_mn": 500.0},
                {"entity_id": "TURN", "month": "2026-05", "nav_date": "2026-05-31", "available_date": "2026-05-31", "nav": 0.998511, "return_1m": 0.03, "assets_cny_mn": 500.0},
                {"entity_id": "TURN", "month": "2026-06", "nav_date": "2026-06-30", "available_date": "2026-06-30", "nav": 1.028466, "return_1m": 0.03, "assets_cny_mn": 500.0},
            ],
            benchmark_monthly=[
                {"month": "2026-01", "benchmark_return_1m": 0.0, "available_date": "2026-01-31"},
                {"month": "2026-02", "benchmark_return_1m": 0.0, "available_date": "2026-02-28"},
                {"month": "2026-03", "benchmark_return_1m": 0.0, "available_date": "2026-03-31"},
                {"month": "2026-04", "benchmark_return_1m": 0.0, "available_date": "2026-04-30"},
                {"month": "2026-05", "benchmark_return_1m": 0.0, "available_date": "2026-05-31"},
                {"month": "2026-06", "benchmark_return_1m": 0.0, "available_date": "2026-06-30"},
            ],
            manager_assignment_monthly=[
                {"entity_id": "TURN", "month": "2026-01", "manager_name": "老经理", "manager_start_month": "2025-01", "manager_end_month": "2026-03"},
                {"entity_id": "TURN", "month": "2026-02", "manager_name": "老经理", "manager_start_month": "2025-01", "manager_end_month": "2026-03"},
                {"entity_id": "TURN", "month": "2026-03", "manager_name": "老经理", "manager_start_month": "2025-01", "manager_end_month": "2026-03"},
                {"entity_id": "TURN", "month": "2026-04", "manager_name": "新经理", "manager_start_month": "2026-04", "manager_end_month": ""},
                {"entity_id": "TURN", "month": "2026-05", "manager_name": "新经理", "manager_start_month": "2026-04", "manager_end_month": ""},
                {"entity_id": "TURN", "month": "2026-06", "manager_name": "新经理", "manager_start_month": "2026-04", "manager_end_month": ""},
            ],
            fund_type_audit=[],
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "TURN", "month": "2026-01", "is_eligible": 1},
            {"entity_id": "TURN", "month": "2026-02", "is_eligible": 1},
            {"entity_id": "TURN", "month": "2026-03", "is_eligible": 1},
            {"entity_id": "TURN", "month": "2026-04", "is_eligible": 1},
            {"entity_id": "TURN", "month": "2026-05", "is_eligible": 1},
            {"entity_id": "TURN", "month": "2026-06", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        month_map = {str(row["month"]): row for row in rows}

        self.assertAlmostEqual(float(month_map["2026-06"]["manager_post_change_excess_delta_12m"]), 0.05, places=6)
        self.assertEqual(int(month_map["2026-06"]["manager_post_change_observation_months"]), 3)
        self.assertIsNone(month_map["2026-04"]["manager_post_change_excess_delta_12m"])

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
        self.assertAlmostEqual(float(month_map["2026-02"]["excess_ret_3m"]), 0.0202, places=6)
        self.assertAlmostEqual(float(month_map["2026-02"]["excess_ret_6m"]), 0.0202, places=6)
        self.assertAlmostEqual(float(month_map["2026-02"]["excess_ret_12m"]), 0.0202, places=6)
        self.assertAlmostEqual(float(month_map["2026-02"]["excess_consistency_12m"]), 1.0, places=6)

    def test_portfolio_limits_single_company_exposure(self) -> None:
        """验证组合构建会遵守单公司暴露约束，且单基金权重不超过上限。"""
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
        self.assertLessEqual(sum(float(row["target_weight"]) for row in portfolio), 1.0)
        self.assertTrue(all(float(row["target_weight"]) <= load_config(config_path).portfolio.single_fund_cap for row in portfolio))

    def test_backtest_respects_next_month_execution(self) -> None:
        """验证回测严格按“当月信号、下月执行”的时间规则运行。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        bundle = prepare_bundle(config_path)

        rows, position_audit_rows = run_backtest(load_config(config_path), bundle["score_rows"], bundle["dataset"].fund_nav_monthly, bundle["dataset"].benchmark_monthly)

        self.assertGreater(len(rows), 0)
        self.assertGreaterEqual(len(position_audit_rows), 0)
        self.assertLess(rows[0]["signal_month"], rows[0]["execution_month"])
        self.assertEqual(rows[0]["execution_request_date_proxy"], f"{rows[0]['execution_month']}-01")
        self.assertEqual(rows[0]["execution_effective_date_proxy"], rows[0]["execution_request_date_proxy"])

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

        rows, _ = run_backtest(config, score_rows, nav_rows, benchmark_rows)

        self.assertEqual([str(row["signal_month"]) for row in rows], ["2026-01", "2026-02"])
        self.assertEqual([str(row["execution_month"]) for row in rows], ["2026-02", "2026-03"])
        self.assertEqual([str(row["execution_request_date_proxy"]) for row in rows], ["2026-02-01", "2026-03-01"])
        self.assertEqual([str(row["execution_effective_date_proxy"]) for row in rows], ["2026-02-01", "2026-03-01"])
        self.assertEqual(int(rows[0]["holdings"]), 1)
        # 2026-02 没有评分结果，因此 2026-02 -> 2026-03 应明确记录为空仓期，而不是被静默跳过。
        self.assertEqual(int(rows[1]["holdings"]), 0)
        # 当前组合构建会受 single_fund_cap 约束，单只基金组合默认不是满仓，因此空仓期净收益只反映卖出成本。
        self.assertEqual(float(rows[1]["portfolio_return_net"]), -0.00015)
        # 从持仓变为空仓意味着发生一次卖出，因此换手不应为 0。
        self.assertEqual(float(rows[1]["turnover"]), 0.15)
        self.assertEqual(str(rows[1]["return_validity"]), "empty_portfolio")
        self.assertEqual(float(rows[1]["missing_weight"]), 0.0)

    def test_backtest_records_missing_return_audit_fields(self) -> None:
        """验证持有期缺失收益会被显式记录到月度回测表和持仓审计表。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_payload = self._base_config(root)
        config_payload["backtest"]["start_month"] = "2026-01"
        config_payload["backtest"]["end_month"] = "2026-02"
        config_payload["portfolio"]["single_fund_cap"] = 0.3
        config = load_config(self._write_config(root, config_payload))
        score_rows = [
            {
                "entity_id": "MISS",
                "month": "2026-01",
                "entity_name": "缺失收益基金",
                "fund_company": "测试公司",
                "primary_type": "主动股票",
                "rank": 1,
                "total_score": 1.0,
            }
        ]
        nav_rows: list[dict[str, object]] = []
        benchmark_rows = [{"month": "2026-02", "benchmark_return_1m": 0.01}]

        rows, position_audit_rows = run_backtest(config, score_rows, nav_rows, benchmark_rows)

        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["missing_weight"]), 0.3)
        self.assertEqual(int(rows[0]["missing_position_count"]), 1)
        self.assertEqual(str(rows[0]["return_validity"]), "all_missing")
        self.assertEqual(int(rows[0]["low_confidence_flag"]), 1)
        self.assertEqual(len(position_audit_rows), 1)
        self.assertEqual(str(position_audit_rows[0]["outcome_status"]), "missing_return")
        self.assertEqual(str(position_audit_rows[0]["observed_return_1m"]), "")
        self.assertEqual(float(position_audit_rows[0]["applied_return_1m"]), 0.0)

    def test_backtest_summary_includes_missing_return_diagnostics(self) -> None:
        """验证回测汇总会把缺失收益月份和权重统计写入摘要。"""
        backtest_rows = [
            {
                "portfolio_return_net": 0.01,
                "benchmark_return": 0.005,
                "missing_weight": 0.0,
                "low_confidence_flag": 0,
                "return_validity": "valid",
            },
            {
                "portfolio_return_net": -0.02,
                "benchmark_return": -0.01,
                "missing_weight": 0.2,
                "low_confidence_flag": 1,
                "return_validity": "partial_missing",
            },
        ]

        summary = summarize_backtest(backtest_rows)

        self.assertEqual(int(summary["missing_month_count"]), 1)
        self.assertEqual(int(summary["low_confidence_month_count"]), 1)
        self.assertAlmostEqual(float(summary["avg_missing_weight"]), 0.1, places=6)
        self.assertAlmostEqual(float(summary["max_missing_weight"]), 0.2, places=6)

    def test_score_funds_respects_configured_category_factors(self) -> None:
        """验证评分引擎会按照配置中的因子集合与权重合成分数，而不是继续写死旧口径。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["ranking"]["factor_weights"] = {
            "performance_quality": 0.5,
            "risk_control": 0.3,
            "stability_quality": 0.2,
        }
        config["ranking"]["category_factors"] = {
            "performance_quality": {"excess_ret_12m": 1.0},
            "risk_control": {"downside_vol_12m": 1.0},
            "stability_quality": {"manager_post_change_excess_delta_12m": 1.0},
        }
        app_config = load_config(self._write_config(root, config))
        feature_rows = [
            {
                "entity_id": "A",
                "month": "2026-02",
                "is_eligible": 1,
                "entity_name": "基金A",
                "fund_company": "公司A",
                "primary_type": "主动股票",
                "benchmark_key": "broad_equity",
                "benchmark_name": "样例基准",
                "manager_name": "经理A",
                "ret_12m": 0.3,
                "ret_6m": 0.5,
                "excess_ret_12m": 0.4,
                "max_drawdown_12m": -0.2,
                "vol_12m": 0.2,
                "downside_vol_12m": 0.05,
                "manager_tenure_months": 60,
                "asset_stability_12m": 2.0,
                "manager_post_change_excess_delta_12m": 0.03,
            },
            {
                "entity_id": "B",
                "month": "2026-02",
                "is_eligible": 1,
                "entity_name": "基金B",
                "fund_company": "公司B",
                "primary_type": "主动股票",
                "benchmark_key": "broad_equity",
                "benchmark_name": "样例基准",
                "manager_name": "经理B",
                "ret_12m": 0.8,
                "ret_6m": 0.1,
                "excess_ret_12m": 0.1,
                "max_drawdown_12m": -0.05,
                "vol_12m": 0.1,
                "downside_vol_12m": 0.08,
                "manager_tenure_months": 12,
                "asset_stability_12m": 0.5,
                "manager_post_change_excess_delta_12m": -0.02,
            },
        ]

        rows = score_funds(app_config, feature_rows)
        row_map = {str(row["entity_id"]): row for row in rows}

        self.assertEqual(float(row_map["A"]["performance_quality"]), 1.0)
        self.assertEqual(float(row_map["B"]["performance_quality"]), 0.0)
        self.assertEqual(float(row_map["A"]["risk_control"]), 1.0)
        self.assertEqual(float(row_map["A"]["stability_quality"]), 1.0)
        self.assertEqual(int(row_map["A"]["rank"]), 1)

    def test_score_funds_assigns_neutral_score_for_missing_event_factor(self) -> None:
        """验证事件类因子缺失时不会把评分流程跑崩，并按中性分处理。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["ranking"]["category_factors"] = {
            "performance_quality": {"excess_ret_12m": 1.0},
            "risk_control": {"downside_vol_12m": 1.0},
            "stability_quality": {"manager_post_change_excess_delta_12m": 1.0},
        }
        app_config = load_config(self._write_config(root, config))
        feature_rows = [
            {
                "entity_id": "A",
                "month": "2026-02",
                "is_eligible": 1,
                "entity_name": "基金A",
                "fund_company": "公司A",
                "primary_type": "主动股票",
                "benchmark_key": "broad_equity",
                "benchmark_name": "样例基准",
                "manager_name": "经理A",
                "ret_12m": 0.3,
                "ret_6m": 0.3,
                "excess_ret_12m": 0.3,
                "max_drawdown_12m": -0.1,
                "vol_12m": 0.1,
                "downside_vol_12m": 0.05,
                "manager_tenure_months": 12,
                "asset_stability_12m": 1.0,
                "manager_post_change_excess_delta_12m": None,
            },
            {
                "entity_id": "B",
                "month": "2026-02",
                "is_eligible": 1,
                "entity_name": "基金B",
                "fund_company": "公司B",
                "primary_type": "主动股票",
                "benchmark_key": "broad_equity",
                "benchmark_name": "样例基准",
                "manager_name": "经理B",
                "ret_12m": 0.2,
                "ret_6m": 0.2,
                "excess_ret_12m": 0.2,
                "max_drawdown_12m": -0.2,
                "vol_12m": 0.2,
                "downside_vol_12m": 0.08,
                "manager_tenure_months": 24,
                "asset_stability_12m": 1.0,
                "manager_post_change_excess_delta_12m": 0.04,
            },
        ]

        rows = score_funds(app_config, feature_rows)
        row_map = {str(row["entity_id"]): row for row in rows}

        self.assertEqual(float(row_map["A"]["stability_quality"]), 0.5)

    def test_score_funds_respects_direction_for_new_observation_fields(self) -> None:
        """验证新观察层字段进入候选评分体系时会按配置方向正确打分。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["ranking"]["category_factors"] = {
            "performance_quality": {"excess_hit_rate_12m": 1.0},
            "risk_control": {"downside_vol_12m": 1.0},
            "stability_quality": {"asset_flow_volatility_12m": 1.0},
        }
        app_config = load_config(self._write_config(root, config))
        feature_rows = [
            {
                "entity_id": "A",
                "month": "2026-02",
                "is_eligible": 1,
                "entity_name": "基金A",
                "fund_company": "公司A",
                "primary_type": "主动股票",
                "benchmark_key": "broad_equity",
                "benchmark_name": "样例基准",
                "manager_name": "经理A",
                "excess_hit_rate_12m": 0.8,
                "downside_vol_12m": 0.05,
                "asset_flow_volatility_12m": 0.1,
            },
            {
                "entity_id": "B",
                "month": "2026-02",
                "is_eligible": 1,
                "entity_name": "基金B",
                "fund_company": "公司B",
                "primary_type": "主动股票",
                "benchmark_key": "broad_equity",
                "benchmark_name": "样例基准",
                "manager_name": "经理B",
                "excess_hit_rate_12m": 0.2,
                "downside_vol_12m": 0.08,
                "asset_flow_volatility_12m": 0.4,
            },
        ]

        rows = score_funds(app_config, feature_rows)
        row_map = {str(row["entity_id"]): row for row in rows}

        self.assertEqual(float(row_map["A"]["performance_quality"]), 1.0)
        self.assertEqual(float(row_map["A"]["stability_quality"]), 1.0)
        self.assertEqual(int(row_map["A"]["rank"]), 1)

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

    def test_fetch_writes_incremental_progress_file(self) -> None:
        """验证 Tushare 抓数会写出独立进度文件，避免长任务期间只能依赖最终快照判断是否停滞。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = self._base_config(root)
        config["data_source"] = "tushare"
        config["tushare"]["download_enabled"] = True
        config["tushare"]["use_cached_raw"] = False
        config["tushare"]["max_funds"] = 2
        config["tushare"]["progress_every_entities"] = 1
        loaded_config = load_config(self._write_config(root, config))
        import pandas as pd

        provider = object.__new__(TushareDataProvider)
        provider.project_root = root
        provider.config = loaded_config
        provider.pd = pd
        provider._manager_df_cache = {}
        provider._monthly_nav_cache = {}
        provider._api_call_stats = defaultdict(lambda: {"calls": 0, "failures": 0, "elapsed_seconds": 0.0})
        provider._api_error_samples = []
        provider._api_last_call_at = {}
        provider._api_min_interval_seconds = {}
        provider._api_cache_hits = defaultdict(int)
        provider._api_cache_misses = defaultdict(int)

        class ClientLike:
            def fund_basic(self, **_: object):
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "000001.OF",
                            "name": "测试成长A",
                            "management": "测试基金",
                            "fund_type": "普通股票型基金",
                            "invest_type": "契约型开放式",
                            "benchmark": "中证800",
                            "status": "L",
                            "found_date": "20200101",
                            "custodian": "托管行甲",
                        },
                        {
                            "ts_code": "000002.OF",
                            "name": "测试价值A",
                            "management": "测试基金",
                            "fund_type": "普通股票型基金",
                            "invest_type": "契约型开放式",
                            "benchmark": "中证800",
                            "status": "L",
                            "found_date": "20200101",
                            "custodian": "托管行乙",
                        },
                    ]
                )

            def fund_company(self):
                return pd.DataFrame([])

        provider.client = ClientLike()
        provider._call_api = lambda _api_name, func, **kwargs: func(**kwargs)  # type: ignore[method-assign]
        provider._fetch_current_manager = lambda ts_code: ("经理甲", "2024-01-01")  # type: ignore[method-assign]
        provider._build_manager_assignment_rows = lambda ts_code, entity_id, entity_nav_rows: []  # type: ignore[method-assign]
        provider._fetch_benchmark_rows = lambda month_set: [{"month": month, "benchmark_return_1m": 0.01} for month in month_set]  # type: ignore[method-assign]

        def fake_fetch_entity_monthly_nav_rows(rows: list[dict[str, object]], entity_id: str) -> tuple[float, list[dict[str, object]]]:
            return 123.0, [
                {
                    "entity_id": entity_id,
                    "month": "2026-02",
                    "nav_date": "2026-02-28",
                    "available_date": "2026-02-28",
                    "nav": 1.0,
                    "return_1m": 0.02,
                    "assets_cny_mn": 123.0,
                }
            ]

        provider._fetch_entity_monthly_nav_rows = fake_fetch_entity_monthly_nav_rows  # type: ignore[method-assign]

        dataset = provider.fetch()

        progress_path = self._scoped_raw_dir(root, "tushare") / "fetch_progress.json"
        self.assertTrue(progress_path.exists())
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        self.assertEqual(progress["status"], "completed")
        self.assertEqual(progress["processed_entities"], 2)
        self.assertEqual(progress["retained_entities"], 2)
        self.assertEqual(progress["requested_max_funds"], 2)
        self.assertEqual(progress["entity_count"], len(dataset.fund_entity_master))
        self.assertEqual(progress["share_class_count"], len(dataset.fund_share_class_map))

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
            provider._force_refresh_api_names = {"fund_basic", "fund_company"}
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

    def test_fund_basic_and_fund_company_force_refresh_even_if_disk_cache_exists(self) -> None:
        """验证 fund_basic 与 fund_company 默认强制刷新，不命中旧的整表接口缓存。"""
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
            provider._force_refresh_api_names = {"fund_basic", "fund_company"}
            provider.pd = pd
            return provider

        class FuncLike:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, **_: object):
                self.calls += 1
                return pd.DataFrame([{"value": self.calls}])

        first_provider = build_provider()
        first_func = FuncLike()
        first_provider._call_api("fund_basic", first_func)
        self.assertEqual(first_func.calls, 1)
        self.assertEqual(first_provider._api_cache_misses["fund_basic"], 1)

        second_provider = build_provider()
        second_func = FuncLike()
        second_provider._call_api("fund_basic", second_func)
        self.assertEqual(second_func.calls, 1)
        self.assertEqual(second_provider._api_cache_hits["fund_basic"], 0)
        self.assertEqual(second_provider._api_cache_misses["fund_basic"], 1)

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
            {"entity_id": "A", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.9, "ret_6m": 0.9, "excess_ret_3m": 0.9, "excess_ret_6m": 0.9, "excess_ret_12m": 0.9, "excess_consistency_12m": 1.0, "max_drawdown_12m": -0.1, "drawdown_recovery_ratio_12m": 0.9, "hit_rate_12m": 0.9, "profit_loss_ratio_12m": 2.0, "worst_3m_avg_return_12m": 0.03, "manager_post_change_excess_delta_12m": 0.04, "vol_12m": 0.05, "downside_vol_12m": 0.03, "manager_tenure_months": 24, "asset_stability_12m": 0.1},
            {"entity_id": "B", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.1, "ret_6m": 0.1, "excess_ret_3m": 0.1, "excess_ret_6m": 0.1, "excess_ret_12m": 0.1, "excess_consistency_12m": 0.0, "max_drawdown_12m": -0.3, "drawdown_recovery_ratio_12m": 0.1, "hit_rate_12m": 0.2, "profit_loss_ratio_12m": 0.5, "worst_3m_avg_return_12m": -0.08, "manager_post_change_excess_delta_12m": -0.02, "vol_12m": 0.2, "downside_vol_12m": 0.15, "manager_tenure_months": 6, "asset_stability_12m": 0.6},
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
        self.assertIn("excess_consistency_12m", row_map)
        self.assertTrue(any(str(row["factor_name"]) == "ret_12m" for row in result["distribution_rows"]))
        self.assertTrue(any(str(row["factor_name"]) == "ret_12m" for row in result["bucket_rows"]))
        self.assertTrue(any(str(row["factor_left"]) == "ret_12m" or str(row["factor_right"]) == "ret_12m" for row in result["correlation_rows"]))

    def test_factor_evaluation_skips_months_without_next_return(self) -> None:
        """验证缺少下一月收益时，因子评估会安全跳过该月而不是报错。"""
        feature_rows = [
            {"entity_id": "A", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.2, "ret_6m": 0.2, "excess_ret_3m": 0.2, "excess_ret_6m": 0.2, "excess_ret_12m": 0.2, "excess_consistency_12m": 1.0, "max_drawdown_12m": -0.1, "drawdown_recovery_ratio_12m": 0.8, "hit_rate_12m": 0.8, "profit_loss_ratio_12m": 1.5, "worst_3m_avg_return_12m": 0.01, "manager_post_change_excess_delta_12m": 0.03, "vol_12m": 0.1, "downside_vol_12m": 0.08, "manager_tenure_months": 12, "asset_stability_12m": 0.2},
            {"entity_id": "B", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.1, "ret_6m": 0.1, "excess_ret_3m": 0.1, "excess_ret_6m": 0.1, "excess_ret_12m": 0.1, "excess_consistency_12m": 0.0, "max_drawdown_12m": -0.2, "drawdown_recovery_ratio_12m": 0.2, "hit_rate_12m": 0.2, "profit_loss_ratio_12m": 0.5, "worst_3m_avg_return_12m": -0.04, "manager_post_change_excess_delta_12m": -0.01, "vol_12m": 0.2, "downside_vol_12m": 0.15, "manager_tenure_months": 8, "asset_stability_12m": 0.3},
        ]
        nav_rows: list[dict[str, object]] = []

        result = evaluate_factors(feature_rows, nav_rows)

        self.assertEqual(int(result["summary"]["factor_count"]), 24)
        self.assertTrue(all(int(row["evaluation_months"]) == 0 for row in result["factor_rows"]))
        self.assertTrue(all(int(row["bucket_evaluation_months"]) == 0 for row in result["bucket_rows"]))

    def test_factor_evaluation_distribution_and_correlation_handle_constant_and_missing_values(self) -> None:
        """验证分布、分层和相关性诊断在常数因子与缺失值下仍能稳定输出。"""
        feature_rows = [
            {"entity_id": "A", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.9, "ret_6m": 0.9, "excess_ret_3m": 0.9, "excess_ret_6m": 0.9, "excess_ret_12m": 0.9, "excess_consistency_12m": 1.0, "max_drawdown_12m": -0.1, "drawdown_recovery_ratio_12m": 0.9, "hit_rate_12m": 0.9, "profit_loss_ratio_12m": 2.0, "worst_3m_avg_return_12m": 0.02, "manager_post_change_excess_delta_12m": 0.04, "vol_12m": 0.1, "downside_vol_12m": 0.05, "manager_tenure_months": 12, "asset_stability_12m": 0.2},
            {"entity_id": "B", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.7, "ret_6m": 0.7, "excess_ret_3m": 0.7, "excess_ret_6m": 0.7, "excess_ret_12m": 0.7, "excess_consistency_12m": 1.0, "max_drawdown_12m": -0.2, "drawdown_recovery_ratio_12m": 0.7, "hit_rate_12m": 0.7, "profit_loss_ratio_12m": 1.5, "worst_3m_avg_return_12m": 0.01, "manager_post_change_excess_delta_12m": 0.03, "vol_12m": 0.2, "downside_vol_12m": 0.09, "manager_tenure_months": 12, "asset_stability_12m": 0.3},
            {"entity_id": "C", "month": "2026-01", "is_eligible": 1, "ret_12m": "", "ret_6m": 0.5, "excess_ret_3m": 0.5, "excess_ret_6m": 0.5, "excess_ret_12m": 0.5, "excess_consistency_12m": 1.0, "max_drawdown_12m": -0.3, "drawdown_recovery_ratio_12m": 0.5, "hit_rate_12m": 0.5, "profit_loss_ratio_12m": 1.0, "worst_3m_avg_return_12m": 0.0, "manager_post_change_excess_delta_12m": 0.02, "vol_12m": 0.3, "downside_vol_12m": 0.12, "manager_tenure_months": 12, "asset_stability_12m": 0.4},
            {"entity_id": "D", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.3, "ret_6m": 0.3, "excess_ret_3m": 0.3, "excess_ret_6m": 0.3, "excess_ret_12m": 0.3, "excess_consistency_12m": 1.0, "max_drawdown_12m": -0.4, "drawdown_recovery_ratio_12m": 0.3, "hit_rate_12m": 0.3, "profit_loss_ratio_12m": 0.7, "worst_3m_avg_return_12m": -0.01, "manager_post_change_excess_delta_12m": 0.01, "vol_12m": 0.4, "downside_vol_12m": 0.18, "manager_tenure_months": 12, "asset_stability_12m": 0.5},
            {"entity_id": "E", "month": "2026-01", "is_eligible": 1, "ret_12m": 0.1, "ret_6m": 0.1, "excess_ret_3m": 0.1, "excess_ret_6m": 0.1, "excess_ret_12m": 0.1, "excess_consistency_12m": 1.0, "max_drawdown_12m": -0.5, "drawdown_recovery_ratio_12m": 0.1, "hit_rate_12m": 0.1, "profit_loss_ratio_12m": 0.5, "worst_3m_avg_return_12m": -0.02, "manager_post_change_excess_delta_12m": 0.0, "vol_12m": 0.5, "downside_vol_12m": 0.24, "manager_tenure_months": 12, "asset_stability_12m": 0.6},
        ]
        nav_rows = [
            {"entity_id": "A", "month": "2026-02", "return_1m": 0.05},
            {"entity_id": "B", "month": "2026-02", "return_1m": 0.04},
            {"entity_id": "C", "month": "2026-02", "return_1m": 0.03},
            {"entity_id": "D", "month": "2026-02", "return_1m": 0.02},
            {"entity_id": "E", "month": "2026-02", "return_1m": 0.01},
        ]

        result = evaluate_factors(feature_rows, nav_rows)
        distribution_map = {str(row["factor_name"]): row for row in result["distribution_rows"]}
        bucket_map = {str(row["factor_name"]): row for row in result["bucket_rows"]}
        correlation_map = {
            (str(row["factor_left"]), str(row["factor_right"])): row
            for row in result["correlation_rows"]
        }

        self.assertEqual(int(distribution_map["ret_12m"]["missing_count"]), 1)
        self.assertEqual(float(distribution_map["manager_tenure_months"]["std"]), 0.0)
        self.assertEqual(int(bucket_map["ret_6m"]["bucket_evaluation_months"]), 1)
        self.assertEqual(int(correlation_map[("ret_6m", "excess_ret_12m")]["high_correlation_flag"]), 1)

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

    def test_backtest_uses_default_market_benchmark(self) -> None:
        """验证回测主口径固定使用 benchmark.default_key，而不是按持仓动态混合 benchmark。"""
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

        rows, _ = run_backtest(config, score_rows, nav_rows, benchmark_rows)

        self.assertEqual(len(rows), 1)
        self.assertNotIn("benchmark_mix", rows[0])
        self.assertAlmostEqual(float(rows[0]["benchmark_return"]), 0.02, places=6)


if __name__ == "__main__":
    unittest.main()
