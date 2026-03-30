from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote
from wsgiref.simple_server import make_server

from fund_research_v2.common.config import AppConfig, load_config
from fund_research_v2.common.io_utils import read_csv, read_json
from fund_research_v2.common.workflows import artifact_dir, candidate_validation_dir, comparison_dir, factor_evaluation_dir, resolve_project_root, robustness_dir


@dataclass(frozen=True)
class ArtifactStatus:
    """描述某个产物文件是否存在以及缺失提示。"""

    path: Path
    label: str
    exists: bool
    hint: str


class OutputRepository:
    """统一读取 outputs 目录下的研究产物，供只读页面层消费。"""

    def __init__(self, config: AppConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root
        self.clean_dir = artifact_dir(config, project_root, config.paths.clean_dir)
        self.result_dir = artifact_dir(config, project_root, config.paths.result_dir)
        self.report_dir = artifact_dir(config, project_root, config.paths.report_dir)
        self.experiment_dir = artifact_dir(config, project_root, config.paths.experiment_dir)
        self.validation_dir = candidate_validation_dir(config, project_root)
        self.robustness_dir = robustness_dir(config, project_root)
        self.factor_evaluation_dir = factor_evaluation_dir(config, project_root)
        self.comparison_dir = comparison_dir(config, project_root)
        self.output_root = self.result_dir.parent

    def artifact_status(self, relative_path: str, label: str, hint: str) -> ArtifactStatus:
        path = self.output_root / relative_path
        return ArtifactStatus(path=path, label=label, exists=path.exists(), hint=hint)

    def read_json(self, relative_path: str) -> dict[str, object] | None:
        path = self.output_root / relative_path
        if not path.exists():
            return None
        payload = read_json(path)
        return payload if isinstance(payload, dict) else None

    def read_csv(self, relative_path: str) -> list[dict[str, object]] | None:
        path = self.output_root / relative_path
        if not path.exists():
            return None
        return read_csv(path)

    def read_text(self, relative_path: str) -> str | None:
        path = self.output_root / relative_path
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def list_report_paths(self) -> list[str]:
        if not self.output_root.exists():
            return []
        report_paths = [
            str(path.relative_to(self.output_root))
            for path in self.output_root.rglob("*.md")
            if path.is_file()
        ]
        return sorted(report_paths)


def serve_web_command(config_path: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    """启动本地只读网站，展示已生成的研究输出。"""
    app = create_web_app(config_path)
    with make_server(host, port, app) as server:
        print(f"Fund Research Viewer running at http://{host}:{port}")
        server.serve_forever()


def create_web_app(config_path: Path) -> Callable:
    """根据配置文件构建只读网站的 WSGI 应用。"""
    config = load_config(config_path)
    project_root = resolve_project_root(config_path)
    repository = OutputRepository(config, project_root)

    def app(environ: dict[str, object], start_response: Callable) -> list[bytes]:
        path = str(environ.get("PATH_INFO", "/"))
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=False)
        if path == "/":
            status, body = render_overview_page(repository)
        elif path == "/backtest":
            status, body = render_backtest_page(repository)
        elif path == "/portfolio":
            status, body = render_portfolio_page(repository)
        elif path == "/reports":
            report_path = query.get("path", [""])[0]
            status, body = render_reports_page(repository, report_path)
        else:
            status, body = (
                "404 Not Found",
                render_page(
                    "Page Not Found",
                    repository,
                    "<section class='empty-state'><h2>Page not found</h2><p>Use the navigation above.</p></section>",
                ),
            )
        start_response(status, [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    return app


def render_overview_page(repository: OutputRepository) -> tuple[str, str]:
    """渲染实验总览页。"""
    report_status = repository.artifact_status(
        "reports/experiment_report.md",
        "实验报告",
        "先运行 `make run-sample` 或 `make run-tushare` 生成完整实验产物。",
    )
    summary_status = repository.artifact_status(
        "result/backtest_summary.json",
        "回测摘要",
        "先运行完整实验或单独执行 `make backtest-sample` / `make backtest-tushare`。",
    )
    portfolio_status = repository.artifact_status(
        "result/portfolio_snapshot.json",
        "组合快照",
        "先运行完整实验或单独执行 `make portfolio-sample` / `make portfolio-tushare`。",
    )
    report_text = repository.read_text("reports/experiment_report.md")
    summary = repository.read_json("result/backtest_summary.json") or {}
    portfolio = repository.read_json("result/portfolio_snapshot.json") or {}
    latest_positions = portfolio.get("portfolio", []) if isinstance(portfolio.get("portfolio"), list) else []
    factor_eval_status = repository.artifact_status(
        "factor_evaluation/factor_evaluation_report.md",
        "因子评估",
        "运行完整实验且非 --fast 模式后，会生成因子评估产物。",
    )
    robustness_status = repository.artifact_status(
        "robustness/robustness_report.md",
        "稳健性分析",
        "运行 `analyze-robustness` 后，会生成稳健性分析产物。",
    )
    validation_status = repository.artifact_status(
        "candidate_validation/candidate_validation_report.md",
        "候选补证",
        "运行 `validate-baseline-candidate` 后，会生成候选补证产物。",
    )
    comparison_status = repository.artifact_status(
        "comparison/comparison_report.md",
        "实验对比",
        "至少有两次完整实验记录后，才会生成实验对比产物。",
    )
    context_rows = parse_markdown_key_values(report_text, "## Experiment Context") if report_text else []
    benchmark_rows = parse_markdown_key_values(report_text, "## Benchmark Mapping") if report_text else []
    summary_rows = [(key, str(value)) for key, value in summary.items()]
    body = [
        "<section class='hero'>",
        f"<p class='eyebrow'>{escape(repository.config.data_source)} local viewer</p>",
        "<h1>Research Overview</h1>",
        "<p>Read-only browser view over the existing outputs artifacts. Strategy logic and result files stay unchanged.</p>",
        "</section>",
        "<section class='grid two'>",
        render_artifact_card(report_status),
        render_artifact_card(summary_status),
        render_artifact_card(portfolio_status),
        render_summary_card("Output Root", str(repository.output_root)),
        "</section>",
        "<section class='panel'>",
        "<h2>Research Sections</h2>",
        "<p>Diagnostic outputs are now grouped into independent folders for faster browsing and cleaner separation from main strategy results.</p>",
        "<div class='grid two'>",
        render_report_entry_card(factor_eval_status, "factor_evaluation/factor_evaluation_report.md"),
        render_report_entry_card(robustness_status, "robustness/robustness_report.md"),
        render_report_entry_card(validation_status, "candidate_validation/candidate_validation_report.md"),
        render_report_entry_card(comparison_status, "comparison/comparison_report.md"),
        "</div></section>",
        "<section class='grid two'>",
        render_definition_table("Experiment Context", context_rows, "Run a full experiment to populate this section."),
        render_definition_table("Benchmark Mapping", benchmark_rows, "Benchmark details appear after experiment outputs exist."),
        "</section>",
        render_definition_table("Backtest Summary", summary_rows, "Backtest summary is not available yet."),
        "<section class='grid four metrics'>",
        render_metric_card("Months", summary.get("months")),
        render_metric_card("Cumulative Return", format_ratio(summary.get("cumulative_return"))),
        render_metric_card("Annualized Return", format_ratio(summary.get("annualized_return"))),
        render_metric_card("Excess Return", format_ratio(summary.get("excess_cumulative_return"))),
        "</section>",
        render_latest_portfolio_preview(latest_positions),
    ]
    return "200 OK", render_page("Research Overview", repository, "".join(body))


def render_backtest_page(repository: OutputRepository) -> tuple[str, str]:
    """渲染回测浏览页。"""
    summary = repository.read_json("result/backtest_summary.json")
    monthly_rows = repository.read_csv("result/backtest_monthly.csv")
    status = repository.artifact_status(
        "result/backtest_monthly.csv",
        "月度回测结果",
        "先运行 `make backtest-sample`、`make backtest-tushare` 或完整实验。",
    )
    if summary is None or monthly_rows is None:
        body = (
            render_artifact_card(status)
            + "<section class='empty-state'><h2>Backtest unavailable</h2>"
            + f"<p>{escape(status.hint)}</p></section>"
        )
        return "200 OK", render_page("Backtest", repository, body)
    curve_rows = build_backtest_curve_rows(monthly_rows)
    low_confidence_rows = [row for row in monthly_rows if int_value(row.get("low_confidence_flag")) == 1]
    highest_turnover_rows = sorted(monthly_rows, key=lambda row: float_value(row.get("turnover")), reverse=True)[:10]
    body = [
        "<section class='hero'>",
        "<p class='eyebrow'>backtest</p>",
        "<h1>Backtest Analysis</h1>",
        "<p>Monthly net returns, benchmark comparison, and reliability diagnostics from current outputs.</p>",
        "</section>",
        "<section class='grid four metrics'>",
        render_metric_card("Cumulative", format_ratio(summary.get("cumulative_return"))),
        render_metric_card("Annualized", format_ratio(summary.get("annualized_return"))),
        render_metric_card("Volatility", format_ratio(summary.get("annualized_volatility"))),
        render_metric_card("Max Drawdown", format_ratio(summary.get("max_drawdown"))),
        render_metric_card("Benchmark", format_ratio(summary.get("benchmark_cumulative_return"))),
        render_metric_card("Excess", format_ratio(summary.get("excess_cumulative_return"))),
        render_metric_card("Missing Months", summary.get("missing_month_count")),
        render_metric_card("Low Confidence", summary.get("low_confidence_month_count")),
        "</section>",
        "<section class='panel'>",
        "<h2>Cumulative Curve</h2>",
        render_line_chart(curve_rows),
        "</section>",
        "<section class='grid two'>",
        render_table(
            "Highest Turnover Months",
            [
                {
                    "execution_month": row.get("execution_month", ""),
                    "portfolio_return_net": format_ratio(row.get("portfolio_return_net")),
                    "benchmark_return": format_ratio(row.get("benchmark_return")),
                    "turnover": format_ratio(row.get("turnover")),
                    "validity": row.get("return_validity", ""),
                }
                for row in highest_turnover_rows
            ],
            ["execution_month", "portfolio_return_net", "benchmark_return", "turnover", "validity"],
            "No turnover records.",
        ),
        render_table(
            "Low Confidence Months",
            [
                {
                    "execution_month": row.get("execution_month", ""),
                    "missing_weight": format_ratio(row.get("missing_weight")),
                    "missing_positions": row.get("missing_position_count", ""),
                    "validity": row.get("return_validity", ""),
                }
                for row in low_confidence_rows
            ],
            ["execution_month", "missing_weight", "missing_positions", "validity"],
            "No low-confidence months were identified.",
        ),
        "</section>",
        render_table(
            "Monthly Returns",
            [
                {
                    "signal_month": row.get("signal_month", ""),
                    "execution_month": row.get("execution_month", ""),
                    "portfolio_return_net": format_ratio(row.get("portfolio_return_net")),
                    "benchmark_return": format_ratio(row.get("benchmark_return")),
                    "turnover": format_ratio(row.get("turnover")),
                    "holdings": row.get("holdings", ""),
                    "validity": row.get("return_validity", ""),
                }
                for row in monthly_rows
            ],
            ["signal_month", "execution_month", "portfolio_return_net", "benchmark_return", "turnover", "holdings", "validity"],
            "No monthly rows available.",
        ),
    ]
    return "200 OK", render_page("Backtest", repository, "".join(body))


def render_portfolio_page(repository: OutputRepository) -> tuple[str, str]:
    """渲染最新组合浏览页。"""
    snapshot = repository.read_json("result/portfolio_snapshot.json")
    target_rows = repository.read_csv("result/portfolio_target_monthly.csv")
    score_rows = repository.read_csv("result/fund_score_monthly.csv") or []
    status = repository.artifact_status(
        "result/portfolio_snapshot.json",
        "组合快照",
        "先运行 `make portfolio-sample`、`make portfolio-tushare` 或完整实验。",
    )
    if snapshot is None or target_rows is None:
        body = (
            render_artifact_card(status)
            + "<section class='empty-state'><h2>Portfolio unavailable</h2>"
            + f"<p>{escape(status.hint)}</p></section>"
        )
        return "200 OK", render_page("Portfolio", repository, body)
    latest_month = str(snapshot.get("latest_month", ""))
    score_preview = [row for row in score_rows if str(row.get("month", "")) == latest_month][:12]
    body = [
        "<section class='hero'>",
        "<p class='eyebrow'>portfolio</p>",
        "<h1>Latest Portfolio Snapshot</h1>",
        "<p>Current recommended holdings for the latest formal research month.</p>",
        "</section>",
        "<section class='grid four metrics'>",
        render_metric_card("Latest Month", latest_month),
        render_metric_card("Eligible Count", snapshot.get("eligible_count")),
        render_metric_card("Portfolio Size", snapshot.get("portfolio_size")),
        render_metric_card("Benchmark", snapshot.get("benchmark_name")),
        "</section>",
        render_table(
            "Selected Portfolio",
            [
                {
                    "rank": row.get("rank", ""),
                    "entity_name": row.get("entity_name", ""),
                    "fund_company": row.get("fund_company", ""),
                    "target_weight": format_ratio(row.get("target_weight")),
                    "total_score": format_decimal(row.get("total_score")),
                }
                for row in target_rows
            ],
            ["rank", "entity_name", "fund_company", "target_weight", "total_score"],
            "No portfolio rows available.",
        ),
        render_table(
            "Top Ranked Candidates",
            [
                {
                    "rank": row.get("rank", ""),
                    "entity_name": row.get("entity_name", ""),
                    "fund_company": row.get("fund_company", ""),
                    "total_score": format_decimal(row.get("total_score")),
                    "research_month_status": row.get("research_month_status", ""),
                }
                for row in score_preview
            ],
            ["rank", "entity_name", "fund_company", "total_score", "research_month_status"],
            "No ranking rows for the latest month.",
        ),
    ]
    return "200 OK", render_page("Portfolio", repository, "".join(body))


def render_reports_page(repository: OutputRepository, report_path: str) -> tuple[str, str]:
    """渲染 Markdown 报告目录和正文。"""
    report_paths = repository.list_report_paths()
    selected_path = normalize_report_path(report_path, report_paths)
    rendered_report = ""
    if selected_path:
        report_text = repository.read_text(selected_path)
        if report_text is not None:
            rendered_report = render_markdown(report_text)
    body = [
        "<section class='hero'>",
        "<p class='eyebrow'>reports</p>",
        "<h1>Markdown Reports</h1>",
        "<p>Open current generated reports directly in the browser. Files are read from the outputs tree on each request.</p>",
        "</section>",
        "<section class='grid reports-layout'>",
        render_report_list(report_paths, selected_path),
        "<article class='panel report-body'>",
    ]
    if selected_path and rendered_report:
        body.append(f"<div class='report-path'>{escape(selected_path)}</div>{rendered_report}")
    elif report_paths:
        body.append("<div class='empty-copy'>Select a report from the left list.</div>")
    else:
        body.append("<div class='empty-copy'>No Markdown reports found. Run a workflow that generates report artifacts first.</div>")
    body.append("</article></section>")
    return "200 OK", render_page("Reports", repository, "".join(body))


def render_page(title: str, repository: OutputRepository, body: str) -> str:
    """渲染站点通用布局。"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} · Fund Research Viewer</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --paper: #fffaf2;
      --ink: #1f2a2b;
      --muted: #5b6668;
      --line: #d9ccb4;
      --accent: #005f73;
      --accent-soft: #dceff2;
      --gain: #1d6f42;
      --loss: #a93226;
      --shadow: 0 12px 30px rgba(31, 42, 43, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Georgia", "Songti SC", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(238, 155, 0, 0.18), transparent 25%),
        linear-gradient(180deg, #f7f1e7 0%, var(--bg) 100%);
    }}
    a {{ color: inherit; }}
    .shell {{ max-width: 1360px; margin: 0 auto; padding: 24px; }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
      padding: 18px 20px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 250, 242, 0.82);
      backdrop-filter: blur(10px);
      box-shadow: var(--shadow);
    }}
    .brand strong {{ display: block; font-size: 1.1rem; }}
    .brand span {{ color: var(--muted); font-size: 0.92rem; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .links a {{
      text-decoration: none;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--paper);
    }}
    .hero, .panel, .artifact-card, .metric-card, .summary-card {{
      border: 1px solid var(--line);
      border-radius: 22px;
      background: rgba(255, 250, 242, 0.94);
      box-shadow: var(--shadow);
    }}
    .hero {{ padding: 28px; margin-bottom: 20px; }}
    .hero h1 {{ margin: 0 0 10px; font-size: 2.2rem; }}
    .hero p {{ margin: 0; color: var(--muted); max-width: 60rem; }}
    .eyebrow {{
      margin: 0 0 12px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.74rem;
      color: var(--accent);
    }}
    .grid {{
      display: grid;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .two {{ grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
    .four {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .reports-layout {{ grid-template-columns: minmax(260px, 320px) 1fr; align-items: start; }}
    .artifact-card, .metric-card, .summary-card, .panel {{ padding: 20px; }}
    .artifact-card h3, .panel h2 {{ margin-top: 0; }}
    .artifact-card p, .summary-card p, .metric-card p, .panel p, .empty-copy {{ color: var(--muted); }}
    .inline-link {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    .muted-inline {{ color: var(--muted); }}
    .status-pill {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      background: var(--accent-soft);
      color: var(--accent);
    }}
    .status-pill.missing {{ background: #fde7dc; color: var(--loss); }}
    .metric-card .value {{ font-size: 1.55rem; margin: 8px 0 0; }}
    .definition-table, table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid rgba(217, 204, 180, 0.75);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    .table-wrapper {{ overflow-x: auto; }}
    .line-chart {{
      width: 100%;
      min-height: 300px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(220, 239, 242, 0.4), rgba(255, 250, 242, 0.3));
      padding: 12px;
    }}
    .chart-meta {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.9rem;
      margin-top: 10px;
    }}
    .report-list a {{
      display: block;
      text-decoration: none;
      padding: 10px 12px;
      border-radius: 12px;
      margin-bottom: 8px;
      border: 1px solid transparent;
    }}
    .report-list a.active {{
      background: var(--accent-soft);
      border-color: rgba(0, 95, 115, 0.15);
    }}
    .report-body {{ min-height: 420px; }}
    .report-body h1, .report-body h2, .report-body h3 {{ margin-top: 1.3em; }}
    .report-body ul {{ padding-left: 1.3rem; }}
    .report-body code {{
      background: #efe5d4;
      padding: 1px 4px;
      border-radius: 5px;
      font-size: 0.92em;
    }}
    .report-path {{
      display: inline-block;
      margin-bottom: 12px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #efe5d4;
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .empty-state {{
      padding: 28px;
      border: 1px dashed var(--line);
      border-radius: 18px;
      background: rgba(255, 250, 242, 0.65);
    }}
    .foot {{
      margin-top: 22px;
      color: var(--muted);
      font-size: 0.88rem;
      text-align: right;
    }}
    @media (max-width: 900px) {{
      .reports-layout {{ grid-template-columns: 1fr; }}
      .shell {{ padding: 16px; }}
      .hero h1 {{ font-size: 1.8rem; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <nav class="nav">
      <div class="brand">
        <strong>Fund Research Viewer</strong>
        <span>data_source={escape(repository.config.data_source)} · output_root={escape(str(repository.output_root))}</span>
      </div>
      <div class="links">
        <a href="/">Overview</a>
        <a href="/backtest">Backtest</a>
        <a href="/portfolio">Portfolio</a>
        <a href="/reports">Reports</a>
      </div>
    </nav>
    {body}
    <div class="foot">Read-only local site. Refresh the page after regenerating outputs.</div>
  </div>
</body>
</html>"""


def render_artifact_card(status: ArtifactStatus) -> str:
    """渲染单个产物状态卡片。"""
    status_label = "ready" if status.exists else "missing"
    status_class = "status-pill" if status.exists else "status-pill missing"
    return (
        "<article class='artifact-card'>"
        f"<div class='{status_class}'>{escape(status_label)}</div>"
        f"<h3>{escape(status.label)}</h3>"
        f"<p>{escape(str(status.path))}</p>"
        f"<p>{escape('Available for browser view.' if status.exists else status.hint)}</p>"
        "</article>"
    )


def render_report_entry_card(status: ArtifactStatus, report_relative_path: str) -> str:
    """渲染首页研究分区入口卡片。"""
    status_label = "ready" if status.exists else "missing"
    status_class = "status-pill" if status.exists else "status-pill missing"
    action = (
        f"<a class='inline-link' href='/reports?path={quote(report_relative_path)}'>Open report</a>"
        if status.exists
        else f"<span class='muted-inline'>{escape(status.hint)}</span>"
    )
    return (
        "<article class='artifact-card'>"
        f"<div class='{status_class}'>{escape(status_label)}</div>"
        f"<h3>{escape(status.label)}</h3>"
        f"<p>{escape(str(status.path))}</p>"
        f"<p>{action}</p>"
        "</article>"
    )


def render_summary_card(title: str, value: object) -> str:
    """渲染简单摘要卡片。"""
    return f"<article class='summary-card'><h3>{escape(title)}</h3><p>{escape(str(value))}</p></article>"


def render_metric_card(title: str, value: object) -> str:
    """渲染指标卡片。"""
    display = "" if value is None else str(value)
    return f"<article class='metric-card'><div class='eyebrow'>{escape(title)}</div><div class='value'>{escape(display)}</div></article>"


def render_definition_table(title: str, rows: list[tuple[str, str]], empty_text: str) -> str:
    """渲染键值型上下文表。"""
    if not rows:
        return f"<section class='panel'><h2>{escape(title)}</h2><p>{escape(empty_text)}</p></section>"
    html_rows = "".join(
        f"<tr><th>{escape(key)}</th><td>{escape(value)}</td></tr>"
        for key, value in rows
    )
    return (
        f"<section class='panel'><h2>{escape(title)}</h2><table class='definition-table'>"
        f"<tbody>{html_rows}</tbody></table></section>"
    )


def render_table(title: str, rows: list[dict[str, object]], columns: list[str], empty_text: str) -> str:
    """渲染通用表格。"""
    if not rows:
        return f"<section class='panel'><h2>{escape(title)}</h2><p>{escape(empty_text)}</p></section>"
    header_html = "".join(f"<th>{escape(column)}</th>" for column in columns)
    row_html = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(row.get(column, '')))}</td>" for column in columns)
        row_html.append(f"<tr>{cells}</tr>")
    return (
        f"<section class='panel'><h2>{escape(title)}</h2>"
        f"<div class='table-wrapper'><table><thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody></table></div></section>"
    )


def render_latest_portfolio_preview(rows: list[dict[str, object]]) -> str:
    """渲染首页的最新组合预览。"""
    if not rows:
        return "<section class='panel'><h2>Latest Portfolio Preview</h2><p>No portfolio snapshot found yet.</p></section>"
    preview_rows = [
        {
            "rank": row.get("rank", ""),
            "entity_name": row.get("entity_name", ""),
            "fund_company": row.get("fund_company", ""),
            "target_weight": format_ratio(row.get("target_weight")),
        }
        for row in rows[:8]
    ]
    return render_table(
        "Latest Portfolio Preview",
        preview_rows,
        ["rank", "entity_name", "fund_company", "target_weight"],
        "No portfolio rows.",
    )


def render_line_chart(rows: list[dict[str, object]]) -> str:
    """渲染回测累计曲线 SVG。"""
    if not rows:
        return "<p>No backtest rows available.</p>"
    width = 1100
    height = 320
    margin = 28
    all_values = []
    for row in rows:
        all_values.extend([float_value(row.get("portfolio_cumulative")), float_value(row.get("benchmark_cumulative"))])
    min_value = min(all_values)
    max_value = max(all_values)
    if min_value == max_value:
        min_value -= 0.01
        max_value += 0.01

    def scale_x(index: int) -> float:
        if len(rows) == 1:
            return width / 2
        return margin + (width - 2 * margin) * (index / (len(rows) - 1))

    def scale_y(value: float) -> float:
        normalized = (value - min_value) / (max_value - min_value)
        return height - margin - normalized * (height - 2 * margin)

    portfolio_points = " ".join(
        f"{scale_x(index):.1f},{scale_y(float_value(row.get('portfolio_cumulative'))):.1f}"
        for index, row in enumerate(rows)
    )
    benchmark_points = " ".join(
        f"{scale_x(index):.1f},{scale_y(float_value(row.get('benchmark_cumulative'))):.1f}"
        for index, row in enumerate(rows)
    )
    labels = [rows[0]["execution_month"], rows[len(rows) // 2]["execution_month"], rows[-1]["execution_month"]]
    return (
        "<div class='line-chart'>"
        f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' aria-label='Cumulative return chart'>"
        f"<line x1='{margin}' y1='{margin}' x2='{margin}' y2='{height - margin}' stroke='#b9ab92' stroke-width='1' />"
        f"<line x1='{margin}' y1='{height - margin}' x2='{width - margin}' y2='{height - margin}' stroke='#b9ab92' stroke-width='1' />"
        f"<polyline fill='none' stroke='#005f73' stroke-width='3' points='{portfolio_points}' />"
        f"<polyline fill='none' stroke='#ca6702' stroke-width='3' points='{benchmark_points}' />"
        "</svg>"
        "<div class='chart-meta'>"
        "<span>Portfolio</span>"
        "<span>Benchmark</span>"
        f"<span>Range: {escape(str(labels[0]))} → {escape(str(labels[-1]))}</span>"
        f"<span>Midpoint: {escape(str(labels[1]))}</span>"
        "</div></div>"
    )


def render_report_list(report_paths: list[str], selected_path: str) -> str:
    """渲染报告列表。"""
    links = []
    for path in report_paths:
        active = " active" if path == selected_path else ""
        label = path.replace("/", " / ")
        class_attr = f" class='{active.strip()}'" if active else ""
        links.append(f"<a{class_attr} href='/reports?path={quote(path)}'>{escape(label)}</a>")
    content = "".join(links) if links else "<div class='empty-copy'>No Markdown reports found.</div>"
    return f"<aside class='panel report-list'><h2>Report Files</h2>{content}</aside>"


def parse_markdown_key_values(markdown_text: str, section_heading: str) -> list[tuple[str, str]]:
    """从特定 Markdown 小节中提取 `- key: value` 列表。"""
    lines = markdown_text.splitlines()
    capture = False
    rows: list[tuple[str, str]] = []
    for line in lines:
        if line.strip() == section_heading:
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture and line.startswith("- ") and ": " in line:
            key, value = line[2:].split(": ", 1)
            rows.append((key.strip(), value.strip()))
    return rows


def build_backtest_curve_rows(monthly_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """把月度收益序列转换成可展示的累计曲线。"""
    portfolio_cumulative = 1.0
    benchmark_cumulative = 1.0
    curve_rows: list[dict[str, object]] = []
    for row in monthly_rows:
        portfolio_cumulative *= 1 + float_value(row.get("portfolio_return_net"))
        benchmark_cumulative *= 1 + float_value(row.get("benchmark_return"))
        curve_rows.append(
            {
                "execution_month": str(row.get("execution_month", "")),
                "portfolio_cumulative": portfolio_cumulative - 1,
                "benchmark_cumulative": benchmark_cumulative - 1,
            }
        )
    return curve_rows


def normalize_report_path(report_path: str, report_paths: list[str]) -> str:
    """把外部 query 参数限制在当前 outputs 树中的真实 Markdown 文件。"""
    if report_path in report_paths:
        return report_path
    return report_paths[0] if report_paths else ""


def render_markdown(markdown_text: str) -> str:
    """把当前项目报告常用的基础 Markdown 转成 HTML。"""
    lines = markdown_text.splitlines()
    html_parts: list[str] = []
    in_list = False
    in_code_block = False
    code_lines: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            html_parts.append(f"<p>{escape(' '.join(part.strip() for part in paragraph_lines if part.strip()))}</p>")
            paragraph_lines = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_parts.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code_block:
                html_parts.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
                in_code_block = False
                code_lines = []
            else:
                in_code_block = True
            continue
        if in_code_block:
            code_lines.append(raw_line)
            continue
        if not line.strip():
            flush_paragraph()
            close_list()
            continue
        if line.startswith("### "):
            flush_paragraph()
            close_list()
            html_parts.append(f"<h3>{escape(line[4:].strip())}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            close_list()
            html_parts.append(f"<h2>{escape(line[3:].strip())}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            close_list()
            html_parts.append(f"<h1>{escape(line[2:].strip())}</h1>")
            continue
        if line.startswith("- "):
            flush_paragraph()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{escape(line[2:].strip())}</li>")
            continue
        close_list()
        paragraph_lines.append(line)
    flush_paragraph()
    close_list()
    if in_code_block:
        html_parts.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
    return "".join(html_parts)


def float_value(value: object) -> float:
    """把宽松输入转为 float。"""
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def int_value(value: object) -> int:
    """把宽松输入转为 int。"""
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def format_ratio(value: object) -> str:
    """格式化比例值。"""
    if value in {"", None}:
        return ""
    return f"{float_value(value):.2%}"


def format_decimal(value: object) -> str:
    """格式化小数值。"""
    if value in {"", None}:
        return ""
    return f"{float_value(value):.6f}"
