# 影视拍摄连续性管理

项目使用 Python 标准库、SQLite 和 `http.server` 管理非线性拍摄中的连续性。场次与镜头分别记录叙事顺序和拍摄顺序，角色、服装、道具、伤痕状态按叙事链检查，冲突可由调整方案或正式豁免处理，镜头只有在无未处理冲突时才能锁定。

## 运行与测试

```bash
python app.py
python -m unittest discover -s tests -v
```

默认端口 `8115`，页面 <http://127.0.0.1:8115>。首次启动创建“雨夜追踪”示例：拍摄顺序与叙事顺序相反，第二场只登记一次状态却回退为轻伤，生成一个跨场伤痕回退冲突（挂在问题场次第二场，标出前镜头 S01/S01-02 与问题镜头 S02/S02-02）。数据库和端口可分别用 `CONTINUITY_DB`、`PORT` 指定。

## 连续性算法

每个元素选择一种规则：

- `stable`：沿叙事顺序状态必须一致。
- `monotonic`：使用 `numeric_value` 比较，数值不能下降，适合伤痕、污损或破坏程度。
- `allowed`：只有预先登记的状态转移才能通过。

检测以**整个项目**为单位按叙事顺序执行（场次叙事序 → 场内镜头叙事序），与剪辑和拍摄顺序无关。元素只在显式登记状态的镜头之间比较：后续场次没有重新登记同字段时沿用最近一次明确状态，一旦回退或出现不允许的转移，就在问题场次（后一镜头所在场）生成冲突，并标出前镜头与问题镜头（含跨场标记）。登记状态或审核调整后会重算整个项目，因此修好旧冲突后暴露出的新下游冲突也会出现。调整方案必须由制片人或场记提出、由另一位审片人批准；批准后写入镜头状态并重新检查全项目。也可以为确实需要保留的冲突写入豁免理由。锁定会再次检查：只要镜头所在场涉及任何未处理（非豁免）冲突，包括前镜头或后镜头落在本场的跨场冲突，就不能锁定；与冲突无关的其他场次不受影响。锁定后直接改状态会失败。报告页按项目视角串联全部场次、元素叙事链和跨场冲突。

## 主要接口

- `POST /api/users`、`POST /api/productions`
- `POST /api/productions/{id}/scenes`、`POST /api/scenes/{id}/shots`
- `POST /api/productions/{id}/elements`、`POST /api/elements/{id}/transitions`
- `POST /api/shots/{id}/states`、`POST /api/scenes/{id}/check`
- `POST /api/conflicts/{id}/plans`、`POST /api/plans/{id}/review`
- `POST /api/conflicts/{id}/exemptions`
- `POST /api/shots/{id}/lock`
- `GET /api/productions/{id}/continuity`
