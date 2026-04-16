# OBE 数据工程任务规范（命名 / 口径 / 表设计）

> 本文档用于规范 OBE 数字化评价系统中 **数据工程侧** 的任务设计、指标口径、表结构与数据交付方式，目标是：
>
> - 提升指标的一致性、可维护性与可解释性
> - 降低数据工程师与后端 / 前端协作成本
> - 支撑私有化部署场景下的长期演进

---

## 2. 表命名规范（Naming Convention）

| 表类型     | 前缀              | 示例                         |
|---------|-----------------|----------------------------|
| 原始业务表   | `ods_*`         | `ods_student_score_detail` |
| 维度表     | `dim_*`         | `dim_student`              |
| 指标事实表   | `fact_metric_*` | `fact_metric_value`        |
| 元数据表    | `meta_*`        | `meta_metric`              |
| 任务与运行记录 | `task_*`        | `task_run_log`             |

---

## 3. 指标口径规范（Metric Definition）

### 3.1 指标必须具备的要素

每一个可对外使用的指标，**必须在元数据表中完整描述**：

- 指标编码（唯一）
- 中文名称
- 业务含义说明
- 计算口径（文字 + 逻辑说明）
- 粒度（学生 / 课程 / 班级 / 专业等）
- 时间粒度（学期 / 学年 / 周 / 自定义）
- 是否可对比（环比 / 同比）

> 口径不清的指标，**禁止进入前端展示**。



### 3.2 指标唯一标识

每一个业务指标，必须有一个 **唯一指标编码（metric_code）**。

#### 编码格式

```
<对象>.<指标含义>.<口径>
```

#### 示例

| metric_code                     | 说明        |
|---------------------------------|-----------|
| student.course.score            | 学生课程得分    |
| course.score.pass_rate          | 课程及格率     |
| major.graduate_requirement.rate | 专业毕业要求达成度 |

---

## 4. 表设计规范（Core Tables）

### 4.1 总体设计原则

- **一套统一指标模型**，避免“一指标一表”的爆炸式增长
- **三张核心事实表**，覆盖 95% 统计与分析需求
- 指标计算结果与展示解耦
- 支持私有化部署、低资源环境

---

### 4.2 指标事实表设计（核心）

采用 **「一套模型 + 三张核心事实表」** 的设计方案。

#### 4.2.1 设计目标

- 所有指标统一存储
- 支持不同业务主体（学生 / 班级 / 课程 / 专业 / 教师）
- 支持多时间粒度
- 支持扩展，不因新增指标而新增表

---

#### 4.2.2 核心事实表一：指标数值表（fact_metric_value）

用于存储 **绝大多数数值型指标**，是系统的事实数据来源（Source of Truth）。

**表结构示例：**

| 字段名          | 类型       | 说明                                                |
|--------------|----------|---------------------------------------------------|
| metric_code  | varchar  | 指标编码                                              |
| entity_type  | varchar  | 主体类型（student/teacher/teaching_plan/major/college） |
| entity_id    | varchar  | 主体 ID (支持数值 ID 或学号/代码等字符串 ID)                     |
| time_type    | varchar  | 时间类型（week/semester/year）                          |
| time_id      | bigint   | 时间 ID                                             |
| metric_value | decimal  | 指标数值                                              |
| created_at   | datetime | 创建时间                                              |

**适用指标示例：**

- 学生总体成绩
- 课程平均分
- 班级及格率

> 设计约束：
>
> - **新增指标 = 新行，而不是新表**
> - 禁止在该表中直接存储 JSON 

---

#### 4.2.3 核心事实表二：多维明细表（fact_metric_detail）

用于存储 **带有动态维度的原子粒度数据**，如「学生 × 考核环节 × 课程目标 × 得分」「教师 × 教学班 × 教学方式 × 学时」等强异构场景。

**设计思路：** 采用 **JSON 存储动态维度** 的方案，兼顾灵活性与查询性能。

| 字段名          | 类型       | 说明               |
|--------------|----------|------------------|
| id           | bigint   | 主键               |
| metric_code  | varchar  | 指标编码             |
| entity_type  | varchar  | 主体类型             |
| entity_id    | varchar  | 主体 ID (支持数值与字符串) |
| time_type    | varchar  | 时间类型             |
| time_id      | bigint   | 时间 ID            |
| dims_json    | json     | 动态维度集合（扁平 KV 结构） |
| metric_value | decimal  | 数值型度量            |
| created_at   | datetime | 创建时间             |

**dims_json 存储示例：**

```json
{"course_id": 501, "exercise_type": "03", "course_target_id": "123"}
```

**适用场景：**

- 学生 × 课程 × 课程目标 × 考核环节 × 得分
- 教师 × 教学班 × 教学方式 × 学时
- 学生 × 课程 × 课程目标 × 达成度

**性能优化策略：**

- 对 **高频查询维度** 使用 MySQL 虚拟列（Generated Column）+ 索引
- 示例：`v_course_id BIGINT GENERATED ALWAYS AS (JSON_EXTRACT(dims_json, '$.course_id')) VIRTUAL`

**维度关联查询方案（获取ID对应的名称）：**

- **高频维度**（如 `course_id`）：建立 **虚拟列 + 索引**，在 SQL 层直接 JOIN 维度表。
- **低频维度**：在 **应用层（Python）批量关联**。先查出 ID 集合，再批量查询维度表，最后在内存中组装。

**设计约束：**

- **dims_json 必须为扁平一层 KV**，禁止嵌套结构
- **维度键名使用 snake_case**，禁止中文键名
- 新增维度 = 修改 JSON 内容，不修改表结构
- 该表是 `fact_metric_value` 的 **数据来源**，可通过定时任务聚合后写入 value 表

---

#### 4.2.4 核心事实表三：指标结构化结果表（fact_metric_struct）

用于存储 **无法用单一数值表达的指标结果**，如排名、分布、区间统计等。

| 字段名         | 类型       | 说明                                  |
|-------------|----------|-------------------------------------|
| metric_code | varchar  | 指标编码                                |
| entity_type | varchar  | 主体类型                                |
| entity_id   | varchar  | 主体 ID                               |
| time_type   | varchar  | 时间类型                                |
| time_id     | bigint   | 时间 ID                               |
| struct_type | varchar  | 结构类型（rank / distribution / segment） |
| struct_json | json     | 结构化结果                               |
| created_at  | datetime | 创建时间                                |

fact_metric_struct 表的任务是存储复合结果集，其逻辑属性决定了它必须具备表达复杂数据的能力。所以 struct_json 字段不需要强制扁平化，它可以（且通常需要）是嵌套结构。

---

## 5. 元数据表规范（Meta Tables）

### 5.1 指标元数据表（meta_metric）

| 字段          | 说明                          |
|-------------|-----------------------------|
| metric_code | 指标编码                        |
| metric_name | 中文名称                        |
| description | 业务说明                        |
| formula     | 计算口径说明                      |
| entity_type | 主体类型                        |
| time_type   | 时间粒度                        |
| owner       | 负责人                         |
| status      | draft / online / deprecated |

---

## 6. 任务与运行记录规范

> **说明**：为保证计算过程可追溯，系统必须记录每次计算任务的起止时间与阶段状态。当前项目采用 **“总-分”式任务结构**。

### 6.1 任务总览概况表（calc_run_state_summary）

用于存储一次完整计算任务（如：点击“重新计算”触发的全局计算）的总体状态。

| 字段名          | 类型       | 说明                                  |
|--------------|----------|-------------------------------------|
| id           | bigint   | 任务 ID                               |
| run_type     | varchar  | 运行状态（running / completed / terminated） |
| start_time   | datetime | 任务开始时间                            |
| end_time     | datetime | 任务结束时间                            |
| ending_cause | text     | 终止原因（任务失败或异常时的 Exception 摘要）     |
| teacher_no   | varchar  | 触发该任务的用户工号                      |

### 6.2 任务运行明细表（calc_run_state）

用于记录任务内部各计算阶段（CalculationStage）的运行情况。

| 字段名        | 类型       | 说明                               |
|------------|----------|----------------------------------|
| id         | bigint   | 子任务 ID (通常为毫秒级时间戳)             |
| parent_id  | bigint   | 关联的总任务 ID                         |
| task_name  | varchar  | 阶段名称 (如：更新学生维度达成数据)              |
| run_type   | varchar  | 阶段状态                             |
| start_time | datetime | 阶段开始时间                           |
| end_time   | datetime | 阶段结束时间                           |
| ending_cause | text     | 阶段终止原因 (记录该阶段特有的错误快照) |

---

## 7. 数据写入原子性规范

## 数据写入原子性规范

写入指标数据前，必须执行 Delete-Insert 策略。 
`DELETE FROM fact_metric_xxx WHERE time_type='week' AND time_id=5 AND metric_code='xxx'; `
确保同一时间粒度下，一个指标只有一份有效数据。

---

## 8. 表的膨胀与分区策略

假设 2 万学生（全校） × 10 门课（每学期） × 20 个明细指标 = 每周 400 万行数据。一年下来 fact_metric_value / fact_metric_detail 会达到 16000 万行级别。 
风险：虽然 MySQL 能抗，但单表过大会导致索引变大、清理历史数据（如删除几年前的数据）变慢。
方案：按 time_id（如周次或学期）对 fact_metric_value / fact_metric_detail 进行 Table Partitioning (表分区)。

---

## 9. 常见反模式与踩坑记录

本节用于记录在 OBE 项目中**已发生或高概率会发生的数据工程反模式**，用于新成员避坑、老成员对齐认知。

### 9.1 一指标一表（Table Explosion）

**表现形式：**

- 每新增一个指标，就新建一张表
- 表名中直接包含业务含义（如 `student_target_score_avg`）

**问题：**

- 表数量失控（上百 / 上千）
- 难以统一查询、复用和治理
- 口径变更需要修改多张表

**规范结论：**

- 禁止一指标一表
- 新增指标 = 向 `fact_metric_value / fact_metric_detail / fact_metric_struct` 插入新行

---

### 9.2 将展示逻辑写进指标计算

**表现形式：**

- 为某个页面“定制”指标
- 指标名中包含 page / chart

**问题：**

- 指标无法复用
- 计算逻辑与前端强耦合

**规范结论：**

- 指标只描述业务事实
- 展示逻辑通过快照表或接口层解决

---

### 9.3 无任务运行记录，靠日志排查问题

**表现形式：**

- 出问题只能翻日志文件
- 无法统计失败率、耗时

**问题：**

- 运维成本高
- 无法评估系统稳定性

**规范结论：**

- 所有任务必须写 task_instance / task_run_log

## 10. 总体设计总结

- ✅ 原始数据与指标数据彻底解耦
- ✅ 指标统一建模，避免表爆炸
- ✅ 支持私有化部署、小数据量场景
- ✅ 为后续数据仓库 / 大数据升级预留空间

> 这套规范的核心思想是：**先工程化，再平台化**。


## 附录 A：完整指标的生命周期示例（以“课程目标达成度”指标链路为例）

本示例展示从原始数据到多级汇总指标的完整链路，采用项目中真实的 `student.exercise_course_target.score` 与 `student.course_target.score` 为例。

---

### A.1 业务背景与指标链路

在 OBE 体系中，学生的最终目标达成度是基于各考核环节（作业/考试）中的题目得分加权计算得来的。其链路如下：

1.  **原子指标 (Fine-grained)**：`student.exercise_course_target.score`
    *   **含义**：学生在某次作业中针对某个课程目标的百分制得分。
2.  **汇总指标 (Aggregated)**：`student.course_target.score`
    *   **含义**：学生在某门课某个课程目标上的累积达成度得分（综合了截止到当前周的所有作业与考试）。

---

### A.2 实现逻辑与存储规范

| 指标编码                                     | 计算方式 & 逻辑核心                                                                                                        | 存储位置 (Table)         | 核心维度 (dims_json)                                      |
|:-----------------------------------------|:-------------------------------------------------------------------------------------------------------------------|:---------------------|:------------------------------------------------------|
| **student.exercise_course_target.score** | **Python (pandas)**: 读取 `raw_exercise_scores`，按 `[学号, 教学班, 作业, 课程目标]` 聚合。计算 `sum(score) / sum(topic_score) * 100`。 | `fact_metric_detail` | `teaching_plan_id`, `exercise_id`, `course_target_id` |
| **student.course_target.score**          | **SQL (Speed-up)**: 读取历史原子指标，关联 `course_target_eval_method` 权重表，进行**累积加权汇总**。                                      | `fact_metric_detail` | `teaching_plan_id`, `course_target_id`                |

---

### A.3 存储行数据示例 (fact_metric_detail)

系统采用 **「指标中心化」** 存储模型，不同粒度的指标共用事实表，通过 `metric_code` 和 `dims_json` 区分。

| metric_code                            | entity_id (学号) | time_id (周) | dims_json (维度快映射)                                                      | metric_value |
|:---------------------------------------|:---------------|:------------|:-----------------------------------------------------------------------|:-------------|
| `student.exercise_course_target.score` | `202001`       | `5`         | `{"teaching_plan_id": 101, "exercise_id": 501, "course_target_id": 1}` | `85.5`       |
| `student.course_target.score`          | `202001`       | `5`         | `{"teaching_plan_id": 101, "course_target_id": 1}`                     | `82.3`       |

---

> **总结**：这种基于「原子指标 + 汇总指标」的解耦设计，既保证了计算的高效性（SQL 累积计算），也支持了数据的多维度追溯与业务复用。
