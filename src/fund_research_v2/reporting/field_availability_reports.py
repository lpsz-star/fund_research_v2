from __future__ import annotations

from pathlib import Path


def render_field_availability_report(path: Path, audit: dict[str, object]) -> None:
    """把字段可得性审计结果写成 Markdown 报告。"""
    summary = audit.get("summary", {}) if isinstance(audit.get("summary"), dict) else {}
    rows = audit.get("rows", []) if isinstance(audit.get("rows"), list) else []
    needs_audit_rows = [row for row in rows if str(row.get("classification") or "") == "needs_audit"]
    snapshot_rows = [row for row in rows if str(row.get("classification") or "") == "snapshot_only"]
    lines = ["# Field Availability Audit", "", "## Summary", ""]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Current Gate", ""])
    lines.extend(
        [
            "- `history_safe`: 可以进入正式基金池、特征、评分与回测信号。",
            "- `snapshot_only`: 只能解释当前快照，不得直接解释历史月份。",
            "- `needs_audit`: 金融语义或实现已部分接通，但尚未证明在 `decision_date` 时点一定可得，暂不应作为正式升级 baseline 的新增依据。",
        ]
    )
    lines.extend(["", "## Needs Audit Fields", ""])
    if needs_audit_rows:
        for row in needs_audit_rows:
            lines.append(
                f"- {row['field_name']}: risk={row.get('risk_level', '')} "
                f"status={row.get('implementation_status', '')} "
                f"notes={row.get('notes', '')}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Snapshot Only Fields", ""])
    if snapshot_rows:
        for row in snapshot_rows:
            lines.append(f"- {row['field_name']}: {row.get('notes', '')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Key Findings", ""])
    lines.extend(
        [
            "- 当前最干净的 PIT 主链路仍是 `fund_nav_monthly.available_date` 与 `fund_nav_pit_daily.available_date`。",
            "- 规模口径已经通过 `visible_assets_cny_mn` 从历史月份解释中剥离出实体主表最新快照。",
            "- 经理月表虽然已经按任职区间投影到月轴，但仍缺单独 `available_date` 证明，属于下一阶段重点审计对象。",
            "- 基金分类与流动性限制目前仍明显依赖当前规则分类或名称规则，暂不应被误解为严格的历史 PIT 字段。",
        ]
    )
    lines.extend(["", "## Detailed Rows", ""])
    for row in rows:
        lines.append(
            f"- {row['field_name']}: class={row.get('classification', '')} "
            f"risk={row.get('risk_level', '')} source={row.get('source_table', '')} "
            f"usage={row.get('used_in_modules', '')}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
