import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fund_research_v2.backtest.engine import run_backtest
from fund_research_v2.cli import main
from fund_research_v2.common.config import load_config
from fund_research_v2.common.workflows import prepare_bundle, run_experiment_command, run_portfolio_command, run_universe_command
from fund_research_v2.data_ingestion.providers import DatasetSnapshot, load_cached_dataset
from fund_research_v2.data_ingestion.providers import TushareDataProvider
from fund_research_v2.features.feature_builder import build_feature_rows
from fund_research_v2.portfolio.construction import build_portfolio


class PipelineTest(unittest.TestCase):
    def _base_config(self, root: Path) -> dict[str, object]:
        return {
            "as_of_date": "2026-03-01",
            "data_source": "sample",
            "lookback_months": 48,
            "local_secret_path": "configs/local.json",
            "universe": {
                "allowed_primary_types": ["主动股票", "偏股混合"],
                "exclude_name_keywords": ["ETF", "联接", "指数", "LOF", "FOF", "QDII", "债", "货币"],
                "min_history_months": 24,
                "min_fund_age_months": 12,
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
                "ts_code": None,
                "name": "sample_benchmark"
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
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        return config_path

    def test_run_experiment_writes_outputs(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_experiment_command(config_path)

        self.assertTrue((root / "outputs" / "clean" / "fund_universe_monthly.csv").exists())
        self.assertTrue((root / "outputs" / "feature" / "fund_feature_monthly.csv").exists())
        self.assertTrue((root / "outputs" / "result" / "fund_score_monthly.csv").exists())
        self.assertTrue((root / "outputs" / "result" / "portfolio_target_monthly.csv").exists())
        self.assertTrue((root / "outputs" / "result" / "portfolio_snapshot.json").exists())
        self.assertTrue((root / "outputs" / "result" / "backtest_summary.json").exists())
        self.assertTrue((root / "outputs" / "reports" / "portfolio_report.md").exists())
        self.assertTrue((root / "outputs" / "reports" / "universe_audit_report.md").exists())
        report_text = (root / "outputs" / "reports" / "experiment_report.md").read_text(encoding="utf-8")
        self.assertIn("Experiment Context", report_text)
        self.assertIn("Latest Ranking Snapshot", report_text)
        self.assertIn("Backtest Summary", report_text)
        portfolio_report = (root / "outputs" / "reports" / "portfolio_report.md").read_text(encoding="utf-8")
        self.assertIn("Decision Context", portfolio_report)
        self.assertIn("Selected Portfolio", portfolio_report)
        universe_audit_report = (root / "outputs" / "reports" / "universe_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("Latest Month Funnel", universe_audit_report)
        self.assertIn("Reason Counts", universe_audit_report)

    def test_run_portfolio_writes_outputs_without_backtest_artifacts(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_portfolio_command(config_path)

        self.assertTrue((root / "outputs" / "result" / "portfolio_target_monthly.csv").exists())
        self.assertTrue((root / "outputs" / "result" / "portfolio_snapshot.json").exists())
        self.assertTrue((root / "outputs" / "reports" / "portfolio_report.md").exists())
        self.assertFalse((root / "outputs" / "result" / "backtest_summary.json").exists())
        report_text = (root / "outputs" / "reports" / "portfolio_report.md").read_text(encoding="utf-8")
        self.assertIn("Top Ranked Candidates", report_text)
        self.assertIn("Selected Portfolio", report_text)
        self.assertIn("High Ranked But Not Selected", report_text)

    def test_run_universe_writes_audit_report(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        run_universe_command(config_path)

        audit_report = (root / "outputs" / "reports" / "universe_audit_report.md").read_text(encoding="utf-8")
        self.assertIn("Audit Context", audit_report)
        self.assertIn("Latest Month Funnel", audit_report)
        self.assertIn("Eligible Funds", audit_report)

    def test_universe_filters_new_fund_and_low_assets(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        bundle = prepare_bundle(config_path)
        latest_month = max(str(row["month"]) for row in bundle["universe"].rows)
        latest_rows = [row for row in bundle["universe"].rows if str(row["month"]) == latest_month]
        reason_map = {str(row["entity_id"]): str(row["reason_codes"]) for row in latest_rows}

        self.assertIn("assets_below_threshold", reason_map["E007"])
        self.assertIn("fund_too_new", reason_map["E007"])

    def test_portfolio_limits_single_company_exposure(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        bundle = prepare_bundle(config_path)
        latest_month = max(str(row["month"]) for row in bundle["score_rows"])
        latest_scores = [row for row in bundle["score_rows"] if str(row["month"]) == latest_month]

        portfolio = build_portfolio(load_config(config_path), latest_scores)

        companies = [str(row["fund_company"]) for row in portfolio]
        self.assertEqual(len(companies), len(set(companies)))
        self.assertAlmostEqual(sum(float(row["target_weight"]) for row in portfolio), 1.0, places=5)

    def test_backtest_respects_next_month_execution(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        bundle = prepare_bundle(config_path)

        rows = run_backtest(load_config(config_path), bundle["score_rows"], bundle["dataset"].fund_nav_monthly, bundle["dataset"].benchmark_monthly)

        self.assertGreater(len(rows), 0)
        self.assertLess(rows[0]["signal_month"], rows[0]["execution_month"])

    def test_manager_tenure_uses_real_manager_start_month(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))

        bundle = prepare_bundle(config_path)
        latest_month = max(str(row["month"]) for row in bundle["feature_rows"])
        latest_rows = [row for row in bundle["feature_rows"] if str(row["month"]) == latest_month]
        tenure_map = {str(row["entity_id"]): int(row["manager_tenure_months"]) for row in latest_rows}

        self.assertEqual(tenure_map["E004"], 26)

    def test_manager_tenure_falls_back_or_clamps_on_bad_manager_start_month(self) -> None:
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
            metadata={},
        )
        universe = type("UniverseLike", (), {"rows": [
            {"entity_id": "FUTURE", "month": "2026-03", "is_eligible": 1},
            {"entity_id": "MISSING", "month": "2026-03", "is_eligible": 1},
        ]})()

        rows = build_feature_rows(config, dataset, universe)
        tenure_map = {str(row["entity_id"]): int(row["manager_tenure_months"]) for row in rows}

        self.assertEqual(tenure_map["FUTURE"], 27)
        self.assertEqual(tenure_map["MISSING"], 22)

    def test_cli_fetch_uses_fetch_command(self) -> None:
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
            "ts_code": "000906.SH",
            "name": "中证800"
        }
        tushare_config["tushare"]["download_enabled"] = False
        tushare_config["tushare"]["use_cached_raw"] = True
        tushare_config_path = self._write_config(root, tushare_config)

        dataset = load_cached_dataset(load_config(tushare_config_path), root)

        self.assertIsNone(dataset)

    def test_entity_assets_are_aggregated_across_share_classes(self) -> None:
        provider = object.__new__(TushareDataProvider)

        def fake_fetch_monthly_nav_rows(ts_code: str, entity_id: str) -> tuple[float, list[dict[str, object]]]:
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

        self.assertEqual(latest_assets, 165.0)
        self.assertEqual(entity_nav_rows[-1]["assets_cny_mn"], 165.0)
        self.assertEqual(entity_nav_rows[0]["assets_cny_mn"], 150.0)
        self.assertEqual(entity_nav_rows[-1]["return_1m"], 0.02)


if __name__ == "__main__":
    unittest.main()
