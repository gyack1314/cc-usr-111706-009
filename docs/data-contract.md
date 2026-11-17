# 新设施投运阶段证据采集资料约定

正式运营公告尚未取得。normal.json 描述两份来源，conflict.json 用同一身份和版次给出不同原文。原文、解释记录和可见状态需要一致，不能用合成资料推断现实设施或排放。

## r2 阶段化记录

staged.json 演示阶段化采集：每步响应可带 `collected_on`（采集日期，阶段化记录必填），正文为 r2 版次记录，类别如下。

- `evidence`：`stage` 取 permitted/construction/energized/operational；`scope=building` 时必填 `building`，`scope=campus` 时不得出现 `building`；`campus` 必填，`site`、`phase`、`contractor`、`notice`、`quantity` 可选；`observed_on` 与 `claim` 必填。
- `retraction`：`target` 为被撤回公告的 notice 或记录身份。
- `alias`：`name` 为承包商新名，`canonical` 为归并后的既有身份。

同一记录身份（notice、撤回对象或更名单元）再次出现时原文必须一致，否则整批回滚。园区级声明的数量口径只与园区级证据对照，不分解到站点；楼栋数按楼栋去重；撤回与改名按采集日期生效，任何日期均可回查当日已知证据与待核范围。
