# 社区口述史馆听读值班台

采编员登记分段口述录音，值班员从固定录音版发行试听与补播单，听众按原号复查补听结果，接班者按交班件追溯实际遍次与源帧。服务使用 Python 3.11 标准库和 SQLite，绑定本机 `127.0.0.1`。小段音频以持久的实播记录代表。

## 运行

```text
python3 -B -m handover.runtime init --data-dir ./museum-data
python3 -B -m handover.runtime serve --data-dir ./museum-data --port 8765
python3 -B check_project.py
python3 -B demo.py
```

控制台提供 `check_project.py` 作为完整回归入口。从工程根目录直接运行原套件可用 `python3 -B -m unittest discover -s tests -t . -v`。样例用独立的临时目录及本机临时端口，执行真实 HTTP 请求并检查交班结果。初始化和启动补齐所需结构，重复使用同一数据目录保留原始入稿、固定版、现场进度、请求和交班件。目录内有 `library.sqlite3`、`channel.sqlite3` 和 `desk.sqlite3`，分别保存目录和节目、现场、受理和交班。一次初始化或运行使用同一数据目录。

## JSON HTTP 接口

写请求发送 JSON 对象，响应返回 JSON 对象或列表。录音主号、修订号、场次号和各类 `request_id` 为非空字符串，路径中的字符串按 URL 路径段编码。`version_id`、`lineup_id`、`take_id`、`archive_id` 和 `actual_id` 为服务生成的正整数。不同操作类别各有自己的请求号空间。

| 方法与路径 | 请求字段 | 成功结果 |
| --- | --- | --- |
| `POST /drafts` | `recording_id`, `revision`, `source`, `total_frames`, `segments` | 已登记原稿 |
| `POST /releases` | `recording_id`, `revision` | 固定录音版及段目录 |
| `GET /releases/{version_id}` | | 固定版及其来源和段目录 |
| `GET /releases/{version_id}/segments/{number}` | | 该版原段 |
| `POST /lineups` | `session_id`, `version_id`, `first`, `last` | 固定播放单、闭合窗与逐段源帧 |
| `GET /lineups/{lineup_id}` | | 原播放单 |
| `POST /takes` | `lineup_id`, `request_id` | 原开遍身份 |
| `POST /takes/{take_id}/steps` | `request_id` | 下一段实播及原实播号 |
| `POST /takes/{take_id}/stop` | `request_id` | `aborted` 结局及已实播数量 |
| `GET /takes/{take_id}` | | `take` 及有序 `plays` |
| `POST /claims` | `request_id`, `version_id`, `first`, `last` | 补听请求当前结果 |
| `GET /claims/{request_id}` | | 按原号恢复并复领补听结果 |
| `GET /sessions/{session_id}/claims/open` | | 此场次固定版的待补和待核请求 |
| `POST /archives` | `session_id`, `request_id` | 原交班件及固定 `facts` |
| `GET /archives/{archive_id}` | | 固定交班件 |

例如 `POST /drafts` 接受 `{"recording_id":"river","revision":"r1","source":"磁带 A","total_frames":40,"segments":[{"number":1,"name":"渡口","start_frame":0,"stop_frame":10}]}`。发布校核各段的字段、段号顺序及半开帧范围。帧位置为整数，起帧可为零，止帧可等于总帧数。相邻段允许首尾相接。原稿中非法段会导致发布拒绝，该修订的更正用新修订号登记。同一修订同参复领，异参冲突。固定目录可有段号缺口，发行及补听闭合窗内的每个整数段均须存在。场次的第一张合法播放单确定场次的版。发布、播放单及遍次保留原身份。

现场遍状态为 `playing`、`finished` 或 `aborted`。开遍、推进与中止支持各自的原号复领。开遍复领的身份固定，现场现状通过遍查询获取。中止针对指定遍，保留已播历史。末段完成即释放声道。请求接收或取到播放单只表示准备，成功持久提交的实播才计入覆盖。

补听 `status` 为 `pending`（待补）、`pending_review`（待核）或 `settled`（已结清）。`settlement` 在未结时为 `null`，结清时含 `request_id`、`take_id` 和有序 `actual_ids`。正式受理先于目标首段实播并且同一遍实际播全闭合窗时结清，无需等该遍结束。已开始的遍仍可满足尚未实播首段的请求，中止后的未结单可在下一遍重新核对。待核按原号查询或同参提交可继续办理。实播、结清和交班各有原号可复查。

交班按场次列遍，按固定版列请求并附实播出处；同版的其他场次实播可以出现在结清出处中，其遍次仍归所属场次。空实播的在播遍也占用声道，必须完成或中止后才能取得新件。原交班请求可复领既成件。

错误响应形如 `{"error":"bad_window"}`。HTTP 400 表示输入、段目录或窗口不合法，404 表示指定对象不存在，409 表示原号异参、场次版冲突、声道忙或尝试推进或中止已终结遍。临时存储争用可返回 503。无新结果的拒绝保留原版、遍次、实播及既成回执。
