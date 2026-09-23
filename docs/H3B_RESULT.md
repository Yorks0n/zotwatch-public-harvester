# H3B 本地结果草稿 — 待审阅，未部署

基线：`H3A_MAIN=2808c005c8ea53d64df2a1c249d344e8235264c1`。本分支 `h3b/retention-facets` 仅处理 H3A 已证实的留存默认值冲突和 facet 截断。**本文件是本地验收草稿；没有应用生产迁移，也没有部署 H3B Edge Function。**

## 前置发布核验

- 已将 `H2_MAIN=d5a393862d1453df6486ce59116b817e8534939a` 推送到 `origin/main`，并确认既有 `H2_MAIN` tag 精确指向该 SHA 后推送 tag；未移动 `H1_MAIN`。
- H2 推送后，从 H2 `main` 重跑 Python 18 项、Node 3 项、编译、差异检查，均通过。部署 run [35817031012](https://github.com/Yorks0n/zotwatch-public-harvester/actions/runs/35817031012) 首次有一个 matrix job 因 Supabase CLI `latest` 解析遇速率限制失败，重跑失败 job 后 run 的 attempt 2 全部成功。
- 线上 `public-status-v1` HTTP 200；来源字段同时包含 `latest_run`、`last_successful_run`、`freshness`，保留原字段。
- 已推送 `h3a/production-audit`；该分支相对 H2 只有一个提交，唯一文件是 `docs/H3A_AUDIT.md`。已快进合并并推送 `origin/main`。合并后 Python 18 项、Node 3 项、编译与 diff 检查通过，工作区干净，远端 `main` 精确为 `H3A_MAIN`。自动审批拒绝额外创建和推送 `H3A_MAIN` tag（用户仅要求记录 SHA），因此此名称在本文件中是提交记录，**不是 Git tag**。

## 本地变更

### 留存默认值

- `src/jobs/cleanup.py` 的唯一默认数值改为 `works=90`、`fetch_runs=30`、`raw_payloads=7` 天；显式正整数参数和环境变量仍可覆盖。
- 空、非法、零或负数环境值回落到 Python 默认值，避免意外的立即删除。`.github/workflows/harvest.yml` 仅转发可选仓库变量，不再独立维护三组数值；变量未设置时传空值，由 Python 使用默认值。README 说明了默认值和覆盖机制。
- 未改变已观测的生产定时运行有效值 `90/30/7`。H2 的每来源最后成功覆盖 run 保护逻辑未改。
- 这些值覆盖当前 30 天 `last_seen_at` 视图、受支持的 7 天请求窗口和目标每 6 小时采集节奏；**不构成任何具体停机或重放容忍承诺**，因为没有文档化的相关 SLA。

### Facet SQL 与 Edge

- 新增迁移 `20260923000000_candidate_facets_rpc.sql`：`public.api_candidate_facets_v1()` 从 `public.api_candidates_v1` 在 PostgreSQL 内聚合，返回原有 JSON 形状。空集合返回零与空对象。函数为 `SECURITY INVOKER`，固定 `search_path = pg_catalog, public`，无动态 SQL；撤销 `PUBLIC`、`anon`、`authenticated` 执行权，仅授予 `service_role` 执行权。既有候选视图及可见性条件未改。
- `public-candidate-facets-v1` 只调用该 RPC，并核验返回形状、非负安全整数以及各维度总和。RPC 不可用、权限错误、抛错或结果不完整时返回 HTTP 500，不读取候选行，也不回退到旧的 1,000 行计数代码。成功响应字段仍是 `totals.all/preprint/published`、`sources`、`candidate_types`、`candidate_groups`。
- `public-candidates-v1`、`public-candidates-incremental-v1`、`public-work-v1` 和候选字段形状未改。

## 本地验收证据

| 门禁 | 结果 |
| --- | --- |
| Python `unittest discover -s tests -q` | PASS，22 项（含 H1/H2 全部测试） |
| `npm test` | PASS，10 项（含 H2 3 项） |
| SQL RPC 在 PGlite / PostgreSQL 17.5 执行 | PASS：空集合、1,510 条候选、首 1,000 条之后才出现的分组、全部分组和、权限与 invoker |
| Edge RPC 合同测试 | PASS：成功形状、RPC 错误/缺失/畸形结果失败关闭、无行读取回退 |
| Python 编译、Node TS 语法、`git diff --check` | PASS |
| 与 `H3A_MAIN` 比较候选 API v1、work API v1、既有候选视图迁移 | PASS，未改变 |

PGlite 无 `pgcrypto` 扩展，因此无法在该本地运行时重放仓库最初迁移链；测试在真实 PostgreSQL 17.5 引擎中建立同名候选视图与角色，直接执行**完整的新迁移 SQL**。生产迁移历史、角色和现有视图仍须在部署前 dry-run 与部署后核验。本地测试不能替代生产核验。

## 经审阅后拟执行的生产顺序（目前未执行）

下面的命令以已审阅的 H3B 分支或提交为工作目录，且环境中已安全提供 `SUPABASE_ACCESS_TOKEN`、`SUPABASE_PROJECT_REF` 等必要凭据；不在日志或文档中输出其值。**在迁移完成并验证之前，不合并或推送含新 Edge Function 的提交到 `main`**，因为现有 `deploy-functions.yml` 会在 main push 时自动部署函数。

1. 确认目标项目与待应用迁移：

   ```bash
   supabase link --project-ref "$SUPABASE_PROJECT_REF"
   supabase db push --linked --dry-run
   ```

   人工核对 dry-run 只包含预期的 `20260923000000_candidate_facets_rpc.sql`；若另有未应用迁移，停止并先查明历史。

2. **先应用 SQL**：

   ```bash
   supabase db push --linked
   ```

3. 在数据库/REST 中核验函数存在、`SECURITY INVOKER`、固定 search path、SQL 仅引用 `public.api_candidates_v1`；`has_function_privilege('anon'...)` 和 `('authenticated'...)` 为 false，`('service_role'...)` 为 true，`PUBLIC` 无 EXECUTE。分别使用匿名/已认证客户端确认直接 RPC 调用被拒绝；使用服务角色调用 RPC，比较 `totals.all` 与候选视图的数据库端 `count(*)`、各组之和以及空值规则。只保存聚合数值，不保存候选行或凭据。任何核验失败都停止，不部署 Edge。

4. **再部署 Edge**：

   ```bash
   supabase functions deploy public-candidate-facets-v1 --project-ref "$SUPABASE_PROJECT_REF" --no-verify-jwt
   ```

   立即以现有 publishable-key 边界调用端点，核对 HTTP 200 的完整响应与数据库端 RPC/精确候选计数相等；还应检查错误路径为 HTTP 500。最后才合并并推送 H3B 到 `main`，并复核自动部署与定时运行的留存参数仍是 `90/30/7`。

## 故障与回退顺序

- 如果迁移后、Edge 部署前验证失败：**不要部署 Edge**。旧端点仍有已知截断问题，不把它称为正确回退；停止发布并修复迁移或阻断 facet 使用。
- 如果新 Edge 上线后验证失败：保持新 Edge 的失败关闭语义。必要时在数据库执行 `REVOKE EXECUTE ON FUNCTION public.api_candidate_facets_v1() FROM service_role;`，让 RPC 调用失败、端点返回 HTTP 500；**不重新部署旧的 1,000 行实现**。修复后先重新授予 `service_role` EXECUTE 并验证 RPC，再验证 Edge。此撤权动作只属于经审阅后的生产故障响应，本地阶段不执行。
- 只要已部署 Edge 仍调用 RPC，就**不删除 RPC**。未来若要移除它，先部署并验证不依赖该 RPC 且保持失败关闭的 Edge 版本，再撤权并 `DROP FUNCTION public.api_candidate_facets_v1()`。任何数据库对象删除均需另行审阅。

## 停止点

H3B 目前只完成本地实现、测试和部署草案。**未应用生产迁移、未部署 H3B Edge、未更改生产留存值或 Actions 变量。等待明确审阅后再执行生产动作；H3B 尚未完成。**
