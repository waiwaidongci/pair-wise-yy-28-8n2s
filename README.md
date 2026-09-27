# 影视拍摄连续性管理

项目使用 Python 标准库、SQLite 和 `http.server` 管理非线性拍摄中的连续性。场次与镜头分别记录叙事顺序和拍摄顺序，角色、服装、道具、伤痕状态按叙事链检查，冲突可由调整方案或正式豁免处理，镜头只有在无未处理冲突时才能锁定。

## 运行与测试

```bash
python app.py
python -m unittest discover -s tests -v
```

默认端口 `8115`，页面 <http://127.0.0.1:8115>。首次启动创建“雨夜追踪”示例，其中拍摄顺序与叙事顺序相反，并生成一个场内伤痕回退冲突和一个跨场回退冲突（第二场未重新登记、沿用上一场状态后数值下降）。数据库和端口可分别用 `CONTINUITY_DB`、`PORT` 指定。

## 连续性算法

每个元素选择一种规则：

- `stable`：沿叙事顺序状态必须一致。
- `monotonic`：使用 `numeric_value` 比较，数值不能下降，适合伤痕、污损或破坏程度。
- `allowed`：只有预先登记的状态转移才能通过。

检测按**整个项目的叙事顺序**执行：所有镜头先按场次 `narrative_order`、再按镜头 `narrative_order` 串成一条链（与剪辑和拍摄顺序无关）。遍历某元素时只记录它**最近一次明确登记的状态**，中间未重新登记该元素的镜头默认沿用该状态；一旦后续镜头发生回退或走了不允许的转移，就在出问题的后一场生成冲突，并标出前后镜头（可能分属不同场次，即跨场冲突，返回字段 `cross_scene` 及双方场次编号）。

调整方案必须由制片人或场记提出、由另一位审片人批准；批准后写入镜头状态并**重新计算整个项目**，其他受影响场次的跨场冲突随之更新或消失。也可以为确实需要保留的冲突写入豁免理由。锁定镜头前会重算并再次检查：本场未处理冲突、或本镜头作为前/后镜头卷入的未处理跨场冲突都会阻止锁定（豁免除外）；锁定后直接改状态会失败。`GET /api/productions/{id}/continuity` 的报告从项目视角串联所有场次、整条叙事链与跨场冲突。

## 主要接口

- `POST /api/users`、`POST /api/productions`
- `POST /api/productions/{id}/scenes`、`POST /api/scenes/{id}/shots`
- `POST /api/productions/{id}/elements`、`POST /api/elements/{id}/transitions`
- `POST /api/shots/{id}/states`、`POST /api/scenes/{id}/check`
- `POST /api/conflicts/{id}/plans`、`POST /api/plans/{id}/review`
- `POST /api/conflicts/{id}/exemptions`
- `POST /api/shots/{id}/lock`
- `GET /api/productions/{id}/continuity`（项目视角报告：场次、叙事链、跨场冲突）
- `GET /api/productions/{id}/conflicts`、`GET /api/scenes/{id}/conflicts`
