from tests.pipeline_base import PipelineTestBase
from tests.pipeline_legacy import PipelineTest as LegacyPipelineTest


class PipelineIntegrationTest(PipelineTestBase):
    """Grouped workflow and end-to-end integration tests."""

    # 完整实验与对比工作流，验证跨模块主链路可以产出一整套研究结果。
    test_run_experiment_writes_outputs = LegacyPipelineTest.test_run_experiment_writes_outputs
    test_compare_experiments_writes_diff_artifacts = LegacyPipelineTest.test_compare_experiments_writes_diff_artifacts
    # CLI 路由测试只关心命令是否正确分发到 workflow 入口。
    test_cli_dispatches_compare_experiments_command = LegacyPipelineTest.test_cli_dispatches_compare_experiments_command
    test_cli_dispatches_analyze_robustness_command = LegacyPipelineTest.test_cli_dispatches_analyze_robustness_command
    # 这些测试覆盖“命令 -> 输出文件/报告”的协同行为，而不是单个纯函数。
    test_fetch_failed_command_writes_retry_summary_and_report = LegacyPipelineTest.test_fetch_failed_command_writes_retry_summary_and_report
    test_run_portfolio_writes_outputs_without_backtest_artifacts = LegacyPipelineTest.test_run_portfolio_writes_outputs_without_backtest_artifacts
    test_analyze_robustness_writes_outputs = LegacyPipelineTest.test_analyze_robustness_writes_outputs
    test_cli_dispatches_fetch_failed_command = LegacyPipelineTest.test_cli_dispatches_fetch_failed_command
    test_run_universe_writes_audit_report = LegacyPipelineTest.test_run_universe_writes_audit_report
    # 组合构建与回测执行规则虽然局部可解释，但这里验证的是主流程中的集成语义。
    test_portfolio_limits_single_company_exposure = LegacyPipelineTest.test_portfolio_limits_single_company_exposure
    test_backtest_respects_next_month_execution = LegacyPipelineTest.test_backtest_respects_next_month_execution
    test_cli_fetch_uses_fetch_command = LegacyPipelineTest.test_cli_fetch_uses_fetch_command
    test_cli_run_portfolio_uses_portfolio_command = LegacyPipelineTest.test_cli_run_portfolio_uses_portfolio_command
