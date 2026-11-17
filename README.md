# 新设施投运阶段证据采集

本项目接收公开来源的原文及关联记录。当前样例只给出部分证据，未决状态不等于业务事实不存在。

来源响应由 transport 校验，domain 解释资料，ledger 保留事务与版本，view 展示当前证据和缺口。样例为合成资料，不访问真实网站。

## 阶段化采集

stages 模块把获批、施工、送电、运营四类证据分别登记（r2 版次记录），每条记录保存来源原文身份（sha256 与地址）、观察日期、采集日期、楼栋位置（园区/站点/分期/楼栋）与声明口径原文。记录类别：

- `evidence`：阶段观察。`scope=building` 必须给出楼栋；`scope=campus` 保留园区级声明（含分期与新增数量口径），不得绑定楼栋，也不会摊派到具体站点。
- `retraction`：公告撤回，按公告身份指向原记录，只追加不删除，原记录转入已撤回列表并保留撤回来源。
- `alias`：承包商改名，把新名归并到既有身份；展示仍保留各记录的原文用名，计数按归并后身份。

楼栋计数一律按楼栋去重：同一楼栋多次送电只计一次。`--on YYYY-MM-DD` 按采集日期回查当日已入库的证据、撤回与待核范围（各楼栋尚缺哪些阶段、哪些园区级声明数量未获楼栋级证据核实）。

在项目根目录执行：

    python -m unittest discover -s tests -v
    python -m compileall -q capture_service tests
    python -m capture_service.cli inspect data/normal.json
    python -m capture_service.cli stages data/staged.json
    python -m capture_service.cli stages data/staged.json --on 2026-05-15

Dockerfile 提供 Linux 环境；docker build -t commissioning . 构建，docker run --rm commissioning 运行样例。
