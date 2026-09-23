# H3A 生产只读审计

审计时间：2026-09-23 03:10–03:13 UTC。范围：留存、候选可见性、来源覆盖与新鲜度、facet 完整性。本文件只记录聚合数值、配置和时间戳；没有记录论文内容、原始载荷或凭据。

## H2 前置门禁与版本边界

- 本地 `main` 从 `H1_MAIN=7dd7790c8afde63bfe0471df6ff5ca7d93938810` 快进合并 H2；`H2_MAIN=d5a393862d1453df6486ce59116b817e8534939a`，并创建本地同名 tag。`H1_MAIN` 未移动。合并后、开始 H3A 前工作区干净。
- 从合并后的 `main` 重跑：Python unittest 18 项通过；Node freshness 测试 3 项通过；`python -m compileall -q src tests`、`git diff --check` 通过；候选 API v1 函数及迁移相对 `H1_MAIN` 无差异。Python 测试使用现有隔离环境 `/Users/yorkson/opt/zotwatch-public-harvester/.venv/bin/python`。
- **部署边界**：截至审计，`origin/main` 仍是 `H1_MAIN`；本地 H2 合并和 tag 均未推送。最近一次生产定时任务（GitHub Actions run `35785644694`，2026-09-22 21:16:44 UTC）运行的是更早的 `2a02181d7c87e89bd75cdbb11b4bc9f277bb7c25`。线上 `public-status-v1` 返回的来源字段只有 `id/name/enabled/updated_at/latest_run`，没有 H2 的 `last_successful_run/freshness`。以下覆盖数据直接从生产 `fetch_runs` 聚合查询得到，**不可表述为 H2 状态端点已部署**。

## 1. 留存配置的实际权威

| 参数 | Python 本地默认值 | `harvest.yml` Actions 回退值 | 仓库 Actions 变量 | 最近生产运行的实际值 |
| --- | ---: | ---: | --- | ---: |
| `WORK_RETENTION_DAYS` | 3 | 90 | 未设置 | 90 |
| `FETCH_RUN_RETENTION_DAYS` | 3 | 30 | 未设置 | 30 |
| `RAW_PAYLOAD_RETENTION_DAYS` | 1 | 7 | 未设置 | 7 |

证据：`src/jobs/cleanup.py` 的 `DEFAULT_*` 与 `_env_int`；`.github/workflows/harvest.yml` 的 job-level `env`；GitHub 仓库 Actions 变量列表只读查询；生产 run `35785644694` 的 `[cleanup] start work_retention_days=90 fetch_run_retention_days=30 raw_payload_retention_days=7`。该生产 run 使用的旧提交中，上述默认值和工作流回退值与本地 H2 相同。未发现该定时 job 的额外 runtime 覆盖：job 直接为三个参数设置环境变量，且仓库变量均未设置。手动运行 CLI 可采用不同环境值，不能用这次定时运行推断所有手动运行。

代码和文档存在不一致：Python 默认 `3/3/1`，而 Actions 回退及 README 所述默认 `90/30/7`。不能将它们视作同一层的默认值。清理以 `works.last_seen_at`、已完成 `fetch_runs.finished_at`、`raw_payloads.fetched_at` 为界；本地 H2 清理代码还保留每个来源最后一个成功覆盖 run，但该 H2 代码尚未在线上定时运行。

## 2. 可见性、请求窗口与采集节奏

- `api_candidates_v1` 在 `supabase/migrations/20260306200000_candidate_api_types.sql` 中要求 `is_candidate_public=true` 且 `last_seen_at >= now() - 30 days`。这是**最近见到时间**的 30 天可见窗口。
- `.github/workflows/harvest.yml` 的计划表达式是 `17 */6 * * *`，即目标每 6 小时一次；GitHub 实际启动时间可延迟。最近一次运行从 21:16:44 UTC 开始，各来源于 21:17 UTC 成功完成。
- 当前支持的 v2 引擎契约将 `candidates.window_days` 固定为 **7**（`ZotWatch/zotwatch/config/models.py` 和 `config-v2.schema.json`）；工作区模板也用 7。`ZotWatch/src/fetch_new.py` 将该窗口用于候选 API 的 `published_at` 请求过滤，CLI 最后还按 7 天过滤推荐。旧 `SourcesConfig` 类单独有 30 天默认值，不能代替当前支持的 v2 契约。
- 生产 `works` 的 90 天留存长于 API 的 30 天 `last_seen_at` 可见窗口；API 可见窗口长于受支持的 7 天请求窗口。不同时间字段意味着这仅是配置范围比较，并非任何 7 天已发表论文都必定已被采集或可见。
- 检查本仓库 README、`docs/operations.md`、H1/H2 结果、引擎契约与工作区模板后，未找到针对采集停机的**明确时长**或完整性要求。H1 的两小时 stale-run 恢复阈值只定义中断 run 何时可自动重试，不是允许停机两小时，也不是来源新鲜度阈值。本审计不设立新的停机容忍度或新鲜度阈值。

## 3. 生产留存与来源覆盖观测

以下计数由生产 PostgREST 对表或视图执行 `Prefer: count=exact` 的 HEAD 查询取得；只查询时间戳和来源状态。时间点为 2026-09-23 03:10:19 UTC（年龄分布的 `fetch_runs` 补查于 03:12:39 UTC）。查询之间不是同一数据库事务，可能有很小的时间漂移。

| 指标 | 观测 |
| --- | ---: |
| `works` 总数 | 43,481 |
| 当前 `api_candidates_v1` 可见候选 | 15,521 |
| `fetch_runs` 总数 | 444 |
| `raw_payloads` 总数 | 0 |
| `works.last_seen_at` 最早 / 最新 | 2026-06-25 04:35:57 / 2026-09-22 21:17:19 UTC |
| 可见候选所对应 `works.last_seen_at` 最早 / 最新 | 2026-08-24 07:30:53 / 2026-09-22 21:17:19 UTC |
| `fetch_runs.started_at` 最早 / 最新 | 2026-08-24 01:59:09 / 2026-09-22 21:17:18 UTC |

| 年龄界线 | `works.last_seen_at` 更早的数量 | `fetch_runs.finished_at` 更早的数量 |
| --- | ---: | ---: |
| 1 天 | 42,868 | 428 |
| 3 天 | 42,073 | 400 |
| 7 天 | 39,996 | 336 |
| 30 天 | 27,960 | 4 |
| 90 天 | 0 | 0 |

生产中没有超过 90 天未见的 work；30 天以上的 work 不在候选视图中。4 个略过 30 天的已完成 run 与定时清理的离散运行相容，不能据此断定清理失败。`raw_payloads=0` 无法用来验证 7 天删除阈值。

| 来源 | 启用 | 最近尝试 | 最近成功覆盖窗口（`window_start` → `fresh_through=window_end`） | 安全游标摘要 | run 数 |
| --- | --- | --- | --- | --- | ---: |
| crossref | 是 | 2026-09-22 21:17:03 UTC，success | 2026-09-22 16:55:48 → 21:17:01 UTC | `updated_from=2026-09-22T21:17:01Z` | 111 |
| arxiv | 是 | 2026-09-22 21:17:07 UTC，success | 2026-09-22 16:55:55 → 21:17:07 UTC | `updated_from=2026-09-22T21:17:07Z` | 111 |
| biorxiv | 是 | 2026-09-22 21:17:09 UTC，success | 2026-09-22 00:00:00 → 21:17:08 UTC | `updated_from=2026-09-22` | 111 |
| medrxiv | 是 | 2026-09-22 21:17:18 UTC，success | 2026-09-22 00:00:00 → 21:17:18 UTC | `updated_from=2026-09-22` | 111 |
| openalex | 否 | 无 | 无已知成功覆盖 | 无 | 0 |

四个启用来源的最近尝试均成功，`fresh_through` 是各自**报告成功的覆盖终点**，不是上游数据完整性的证明。biorxiv/medrxiv 的日期型游标与窗口终点精度不同。上述测量不能证明历史完整性、上游无遗漏，亦不能推出固定的新鲜度达标标准。OpenAlex 保持禁用。

## 4. 线上 facet 完整性

`public-candidate-facets-v1` 当前一次性 `.select("source,candidate_type,candidate_group,is_preprint")`，然后在 Edge Function 中逐行计数，没有分页。仓库 `supabase/config.toml` 配置 `api.max_rows=1000`；生产 REST 对候选视图请求 `limit=2000` 实际只返回 1,000 行。这个生产探测直接确认了生效的返回上限，不仅依赖本地配置。

生产 facet 端点 HTTP 200，但 `totals.all=1,000`，数据库端对**同一个候选视图**的精确计数是 **15,521**，少算 **14,521**。下面的权威分组数分别通过候选视图上的数据库端 `count=exact` 与维度过滤得到；维度值只用于发现分组，没有输出个体候选行。各组之和均为 15,521。

| 维度 | 线上 facet | 数据库精确计数 |
| --- | ---: | ---: |
| all | 1,000 | 15,521 |
| preprint | 173 | 5,119 |
| published | 827 | 10,402 |
| source: crossref | 837 | 10,646 |
| source: arxiv | 74 | 1,935 |
| source: biorxiv | 50 | 2,107 |
| source: medrxiv | 39 | 833 |
| group: article | 784 | 9,958 |
| group: bookish | 43 | 439 |
| group: dataset | 未返回 | 5 |
| group: preprint | 173 | 5,119 |

| `candidate_type` | 线上 facet | 数据库精确计数 |
| --- | ---: | ---: |
| book | 3 | 44 |
| book-chapter | 35 | 323 |
| book-section | 1 | 2 |
| component | 4 | 43 |
| database | 未返回 | 1 |
| dataset | 未返回 | 5 |
| dissertation | 未返回 | 32 |
| edited-book | 2 | 42 |
| journal | 未返回 | 7 |
| journal-article | 752 | 9,449 |
| journal-issue | 未返回 | 1 |
| monograph | 5 | 72 |
| other | 1 | 73 |
| peer-review | 5 | 10 |
| preprint | 173 | 5,119 |
| proceedings-article | 19 | 230 |
| reference-entry | 未返回 | 32 |
| report | 未返回 | 34 |
| standard | 未返回 | 2 |

**分类：已证实截断且计数不准确。** 这同时解释了为何端点成功并不能证明 facet 完整。精确 count 是数据库执行的过滤计数，可适用于超过 1,000 行的总体；多个请求不是事务快照，但本次分组之和与总数一致，且差距远超并发写入可能造成的微小漂移。

## 5. 仅供审阅的 H3B 最小修正提案（未实施）

### 留存配置

建议把 **90/30/7 天**定为唯一明确的默认组合：将 Python 常量及 README 的本地说明对齐到目前 Actions 工作流回退值；定时生产的配置权威保持在工作流 job-level `env`，仓库 Actions 变量仅作为显式覆盖，并在运行日志中继续输出最终数值。不要在三个位置维护互相冲突的“默认”。90 天 work 留存覆盖 30 天 API 可见窗口，30 天视图覆盖当前支持的 7 天请求窗口，计划每 6 小时采集一次；30 天 run 历史配合 H2 对最后成功覆盖 run 的保留逻辑用于报告覆盖，7 天 raw payload 留存是当前生产设置。由于尚无已定义的停机/重放容忍时长，这组参数**不能被宣称满足某个具体停机承诺**；如产品要承诺时长，应先明确要求，再校核各来源游标及 API 可见性。H3A 不修改任何数值。

### Facet 计数

建议新建单一数据库对象 `public.api_candidate_facets_v1()`（SQL RPC，返回与现有端点相同形状的 JSON）：在数据库中从 `public.api_candidates_v1` 聚合 `all/preprint/published` 以及 `source/candidate_type/candidate_group` 分组；空集合返回零和空对象。函数使用 `SECURITY INVOKER`、固定 `search_path`，只引用该候选视图；撤销 `PUBLIC` 执行权，仅授予 `service_role` 的 `EXECUTE`，沿用当前 Edge Function 的服务端 secret key，不增加 anon/authenticated 的直接 RPC 访问。现有视图/RLS 与服务角色边界保持不变。`public-candidate-facets-v1` Edge Function 只改为调用此 RPC 并透传既有响应形状及错误处理，不下载候选行。迁移与 Edge 部署需联动：先创建并授权 RPC，再部署 Edge；回滚时先将 Edge 恢复到旧版本或可回退版本，再撤销授权并 `DROP FUNCTION public.api_candidate_facets_v1()`。由于旧版本在超过 1,000 行时仍不准确，实际回滚还应保留故障标记或暂停依赖该 facet 的决策。

此提案不涉及 `public-candidates-v1`、`public-candidates-incremental-v1`、`public-work-v1` 或候选载荷字段形状。H3B 必须经本审计明确审阅后另行实施。

## 6. 生产安全确认

H3A 只执行 GitHub Actions 变量/运行日志的只读查询，以及 Supabase REST/Edge 的 GET、HEAD 查询。**未发生生产配置、数据库、数据、迁移、Edge Function、Actions 变量或部署的修改**；未手动清理、回填、重建索引、重置游标或启用 OpenAlex。本地 H2 合并/tag 属于 H3A 前置版本操作，未推送远端。本审计到此停止，不启动 H3B。
