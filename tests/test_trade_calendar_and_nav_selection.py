import shutil
import sys
import tempfile
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd

from fund_research_v2.common.config import load_config
from fund_research_v2.common.contracts import DatasetSnapshot
from fund_research_v2.common.date_utils import decision_date_for_month, first_trading_day_of_month, is_available_by_decision_date, last_trading_day_of_month, next_trading_day
from fund_research_v2.data_ingestion.providers import TushareDataProvider, _select_point_in_time_nav_rows, load_cached_dataset, persist_dataset
from fund_research_v2.data_processing.sample_data import generate_sample_dataset
from fund_research_v2.features.feature_builder import build_feature_rows
from fund_research_v2.universe.filters import build_universe
from tests.pipeline_base import PipelineTestBase


class TradeCalendarAndNavSelectionTest(PipelineTestBase):
    """交易日历与净值版本选择回归测试。"""

    def test_trading_day_helpers_use_cached_trade_calendar(self) -> None:
        """验证交易日历工具函数按开市日计算月初、月末和下一交易日。"""
        trade_calendar_rows = [
            {"exchange": "SSE", "cal_date": "2025-08-01", "is_open": 1, "pretrade_date": "2025-07-31"},
            {"exchange": "SSE", "cal_date": "2025-08-02", "is_open": 0, "pretrade_date": "2025-08-01"},
            {"exchange": "SSE", "cal_date": "2025-08-03", "is_open": 0, "pretrade_date": "2025-08-01"},
            {"exchange": "SSE", "cal_date": "2025-08-04", "is_open": 1, "pretrade_date": "2025-08-01"},
            {"exchange": "SSE", "cal_date": "2025-08-29", "is_open": 1, "pretrade_date": "2025-08-28"},
        ]

        self.assertEqual(first_trading_day_of_month("2025-08", trade_calendar_rows), "2025-08-01")
        self.assertEqual(last_trading_day_of_month("2025-08", trade_calendar_rows), "2025-08-29")
        self.assertEqual(next_trading_day("2025-08-01", trade_calendar_rows), "2025-08-04")
        self.assertEqual(decision_date_for_month("2025-07", trade_calendar_rows), "2025-08-01")
        self.assertTrue(is_available_by_decision_date("2025-08-01", "2025-07", trade_calendar_rows))
        self.assertFalse(is_available_by_decision_date("2025-08-04", "2025-07", trade_calendar_rows))

    def test_select_point_in_time_nav_rows_prefers_earliest_valid_announcement(self) -> None:
        """验证同一 nav_date 多版本时，优先选择最早公告且净值有效的版本。"""
        nav_df = pd.DataFrame(
            [
                {
                    "ts_code": "015640.OF",
                    "nav_date": "20250930",
                    "ann_date": "20251028",
                    "adj_nav": 1.6737,
                    "unit_nav": 1.6737,
                    "accum_nav": 1.6737,
                    "net_asset": 275893.42,
                    "total_netasset": None,
                    "update_flag": "1",
                    "nav_numeric": 1.6737,
                    "asset_numeric": 275.89342,
                    "normalized_available_date": "20251028",
                },
                {
                    "ts_code": "015640.OF",
                    "nav_date": "20250930",
                    "ann_date": "20251001",
                    "adj_nav": 1.6737,
                    "unit_nav": 1.6737,
                    "accum_nav": 1.6737,
                    "net_asset": None,
                    "total_netasset": None,
                    "update_flag": "0",
                    "nav_numeric": 1.6737,
                    "asset_numeric": 2.0,
                    "normalized_available_date": "20251001",
                },
                {
                    "ts_code": "015640.OF",
                    "nav_date": "20250930",
                    "ann_date": "20251028",
                    "adj_nav": 1.6737,
                    "unit_nav": 1.6737,
                    "accum_nav": 1.6737,
                    "net_asset": 275893.42,
                    "total_netasset": None,
                    "update_flag": "1",
                    "nav_numeric": 1.6737,
                    "asset_numeric": 275.89342,
                    "normalized_available_date": "20251028",
                },
            ]
        )

        selected = _select_point_in_time_nav_rows(nav_df)

        self.assertEqual(len(selected), 1)
        row = selected.iloc[0]
        self.assertEqual(str(row["ann_date"]), "20251001")
        self.assertEqual(str(row["update_flag"]), "0")

    def test_fetch_monthly_nav_rows_uses_earliest_valid_ann_date(self) -> None:
        """验证月频净值表继承研究唯一版本的最早可见日期。"""
        provider = object.__new__(TushareDataProvider)
        provider.config = type(
            "ConfigLike",
            (),
            {
                "tushare": type("TushareLike", (), {"start_date": "20250901", "end_date": "20251031", "fund_market": "O"})(),
            },
        )()
        provider.client = type("ClientLike", (), {"fund_nav": object(), "fund_share": object()})()
        provider._monthly_nav_cache = {}

        nav_df = pd.DataFrame(
            [
                {
                    "ts_code": "015640.OF",
                    "ann_date": "20251028",
                    "nav_date": "20250930",
                    "unit_nav": 1.6737,
                    "accum_nav": 1.6737,
                    "adj_nav": 1.6737,
                    "net_asset": 275893.42,
                    "total_netasset": None,
                    "update_flag": "1",
                },
                {
                    "ts_code": "015640.OF",
                    "ann_date": "20251001",
                    "nav_date": "20250930",
                    "unit_nav": 1.6737,
                    "accum_nav": 1.6737,
                    "adj_nav": 1.6737,
                    "net_asset": None,
                    "total_netasset": None,
                    "update_flag": "0",
                },
            ]
        )
        share_df = pd.DataFrame([{"trade_date": "20250929", "fd_share": 200.0}])

        def fake_call_api(api_name, _func, **kwargs):
            if api_name == "fund_nav":
                return nav_df
            if api_name == "fund_share":
                return share_df
            return None

        provider._call_api = fake_call_api  # type: ignore[method-assign]

        latest_assets, daily_rows, monthly_rows = provider._fetch_monthly_nav_rows("015640.OF", "测试基金::测试基金")

        self.assertEqual(latest_assets, 3.347)
        self.assertEqual(len(daily_rows), 1)
        self.assertEqual(daily_rows[0]["available_date"], "2025-10-01")
        self.assertEqual(len(monthly_rows), 1)
        self.assertEqual(monthly_rows[0]["available_date"], "2025-10-01")
        self.assertEqual(monthly_rows[0]["selected_update_flag"], "0")

    def test_persist_and_load_dataset_roundtrip_trade_calendar(self) -> None:
        """验证 trade_calendar 会随 raw 缓存一起持久化和回读。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-trade-calendar-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config_path = self._write_config(root, self._base_config(root))
        config = load_config(config_path)
        dataset = generate_sample_dataset(config.lookback_months, config.benchmark)

        persist_dataset(config, root, dataset)
        loaded = load_cached_dataset(config, root)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertTrue(len(loaded.trade_calendar) > 0)
        self.assertTrue(len(loaded.fund_nav_pit_daily) > 0)
        self.assertIn("cal_date", loaded.trade_calendar[0])
        self.assertIn("trade_date", loaded.fund_nav_pit_daily[0])

    def test_month_end_nav_announced_on_next_day_is_eligible_by_first_trading_day(self) -> None:
        """验证月末净值若在下月第 1 个交易日公告，仍可用于该估值月信号。"""
        root = Path(tempfile.mkdtemp(prefix="fund-research-v2-decision-date-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        config = load_config(self._write_config(root, self._base_config(root)))
        dataset = DatasetSnapshot(
            fund_entity_master=[
                {
                    "entity_id": "LATE",
                    "entity_name": "晚一日公告基金",
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
                {"entity_id": "LATE", "month": "2026-01", "nav_date": "2026-01-30", "available_date": "2026-02-02", "nav": 1.0, "return_1m": 0.01, "assets_cny_mn": 500.0},
                {"entity_id": "LATE", "month": "2026-02", "nav_date": "2026-02-27", "available_date": "2026-03-02", "nav": 1.05, "return_1m": 0.05, "assets_cny_mn": 520.0},
            ],
            benchmark_monthly=[
                {"month": "2026-01", "benchmark_return_1m": 0.0, "available_date": "2026-02-02"},
                {"month": "2026-02", "benchmark_return_1m": 0.0, "available_date": "2026-03-02"},
            ],
            manager_assignment_monthly=[],
            fund_type_audit=[],
            fund_liquidity_audit=[],
            trade_calendar=[
                {"exchange": "SSE", "cal_date": "2026-02-02", "is_open": 1, "pretrade_date": "2026-01-30"},
                {"exchange": "SSE", "cal_date": "2026-02-03", "is_open": 1, "pretrade_date": "2026-02-02"},
                {"exchange": "SSE", "cal_date": "2026-03-02", "is_open": 1, "pretrade_date": "2026-02-27"},
                {"exchange": "SSE", "cal_date": "2026-03-03", "is_open": 1, "pretrade_date": "2026-03-02"},
            ],
            metadata={},
        )

        universe = build_universe(config, dataset)
        feature_rows = build_feature_rows(config, dataset, universe)

        universe_map = {str(row["month"]): row for row in universe.rows}
        feature_map = {str(row["month"]): row for row in feature_rows}
        self.assertEqual(universe_map["2026-01"]["decision_date"], "2026-02-02")
        self.assertEqual(int(universe_map["2026-01"]["is_eligible"]), 0)
        self.assertIn("insufficient_history", str(universe_map["2026-01"]["reason_codes"]))
        self.assertNotIn("nav_not_available_by_decision_date", str(universe_map["2026-01"]["reason_codes"]))
        self.assertEqual(universe_map["2026-02"]["decision_date"], "2026-03-02")
        self.assertNotIn("nav_not_available_by_decision_date", str(universe_map["2026-02"]["reason_codes"]))
        self.assertEqual(feature_map["2026-02"]["decision_date"], "2026-03-02")
