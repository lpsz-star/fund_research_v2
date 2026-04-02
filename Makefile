PYTHON := PYTHONPATH=src python3
APP := -m fund_research_v2
SAMPLE_CONFIG := configs/default.json
TUSHARE_CONFIG := configs/tushare.json
TUSHARE_CANDIDATE_CONFIG := configs/candidates/tushare_scoring_v5_candidate.json

.PHONY: help
help:
	@printf "%s\n" \
	"可用命令：" \
	"  make test                 运行测试" \
	"  make fetch-sample         生成 sample 原始数据缓存" \
	"  make fetch-tushare        拉取 tushare 原始数据缓存" \
	"  make fetch-failed-tushare 仅重抓上次失败的 tushare 份额接口缓存" \
	"  make compare-sample       对比 sample 最近两次完整实验" \
	"  make compare-tushare      对比 tushare 最近两次完整实验" \
	"  make run-tushare-candidate 运行当前 tushare 正式候选完整实验" \
	"  make run-tushare-candidate-fast 运行当前 tushare 正式候选快速实验" \
	"  make analyze-tushare-candidate 运行当前 tushare 正式候选稳健性分析" \
	"  make validate-tushare-candidate 对当前 tushare 正式候选执行 A/B 候选基线验证" \
	"  make validate-tushare-v2  兼容旧入口，等价于 validate-tushare-candidate" \
	"  make universe-sample      构建 sample 基金池" \
	"  make universe-tushare     构建 tushare 基金池" \
	"  make features-sample      计算 sample 特征" \
	"  make features-tushare     计算 tushare 特征" \
	"  make rank-sample          运行 sample 排名流程" \
	"  make rank-tushare         运行 tushare 排名流程" \
	"  make portfolio-sample     运行 sample 组合流程" \
	"  make portfolio-tushare    运行 tushare 组合流程" \
	"  make backtest-sample      运行 sample 回测流程" \
	"  make backtest-tushare     运行 tushare 回测流程" \
	"  make run-sample           运行 sample 完整实验" \
	"  make run-tushare          运行 tushare 完整实验" \
	"  make run-tushare-fast     运行 tushare 快速实验（跳过因子评估与实验对比刷新）" \
	"  make serve-web-sample     启动 sample 本地只读网站" \
	"  make serve-web-tushare    启动 tushare 本地只读网站" \
	"  make clean-outputs        清理 outputs 目录" \
	"  make clean-raw            清理 data/raw 目录"

.PHONY: test
test:
	python3 -m unittest discover -s tests

.PHONY: fetch-sample
fetch-sample:
	$(PYTHON) $(APP) fetch --config $(SAMPLE_CONFIG)

.PHONY: fetch-tushare
fetch-tushare:
	$(PYTHON) $(APP) fetch --config $(TUSHARE_CONFIG)

.PHONY: fetch-failed-tushare
fetch-failed-tushare:
	$(PYTHON) $(APP) fetch-failed --config $(TUSHARE_CONFIG)

.PHONY: compare-sample
compare-sample:
	$(PYTHON) $(APP) compare-experiments --config $(SAMPLE_CONFIG)

.PHONY: compare-tushare
compare-tushare:
	$(PYTHON) $(APP) compare-experiments --config $(TUSHARE_CONFIG)

.PHONY: run-tushare-candidate run-tushare-candidate-fast analyze-tushare-candidate validate-tushare-candidate validate-tushare-v2
run-tushare-candidate:
	$(PYTHON) $(APP) run-experiment --config $(TUSHARE_CANDIDATE_CONFIG)

run-tushare-candidate-fast:
	$(PYTHON) $(APP) run-experiment --config $(TUSHARE_CANDIDATE_CONFIG) --fast

analyze-tushare-candidate:
	$(PYTHON) $(APP) analyze-robustness --config $(TUSHARE_CANDIDATE_CONFIG)

validate-tushare-candidate:
	$(PYTHON) $(APP) validate-baseline-candidate --config $(TUSHARE_CANDIDATE_CONFIG)

validate-tushare-v2: validate-tushare-candidate

.PHONY: universe-sample
universe-sample:
	$(PYTHON) $(APP) build-universe --config $(SAMPLE_CONFIG)

.PHONY: universe-tushare
universe-tushare:
	$(PYTHON) $(APP) build-universe --config $(TUSHARE_CONFIG)

.PHONY: features-sample
features-sample:
	$(PYTHON) $(APP) compute-features --config $(SAMPLE_CONFIG)

.PHONY: features-tushare
features-tushare:
	$(PYTHON) $(APP) compute-features --config $(TUSHARE_CONFIG)

.PHONY: rank-sample
rank-sample:
	$(PYTHON) $(APP) run-ranking --config $(SAMPLE_CONFIG)

.PHONY: rank-tushare
rank-tushare:
	$(PYTHON) $(APP) run-ranking --config $(TUSHARE_CONFIG)

.PHONY: portfolio-sample
portfolio-sample:
	$(PYTHON) $(APP) run-portfolio --config $(SAMPLE_CONFIG)

.PHONY: portfolio-tushare
portfolio-tushare:
	$(PYTHON) $(APP) run-portfolio --config $(TUSHARE_CONFIG)

.PHONY: backtest-sample
backtest-sample:
	$(PYTHON) $(APP) run-backtest --config $(SAMPLE_CONFIG)

.PHONY: backtest-tushare
backtest-tushare:
	$(PYTHON) $(APP) run-backtest --config $(TUSHARE_CONFIG)

.PHONY: run-sample
run-sample:
	$(PYTHON) $(APP) run-experiment --config $(SAMPLE_CONFIG)

.PHONY: run-tushare
run-tushare:
	$(PYTHON) $(APP) run-experiment --config $(TUSHARE_CONFIG)

.PHONY: run-tushare-fast
run-tushare-fast:
	$(PYTHON) $(APP) run-experiment --config $(TUSHARE_CONFIG) --fast

.PHONY: serve-web-sample
serve-web-sample:
	$(PYTHON) $(APP) serve-web --config $(SAMPLE_CONFIG)

.PHONY: serve-web-tushare
serve-web-tushare:
	$(PYTHON) $(APP) serve-web --config $(TUSHARE_CONFIG)

.PHONY: clean-outputs
clean-outputs:
	rm -rf outputs

.PHONY: clean-raw
clean-raw:
	rm -rf data/raw
