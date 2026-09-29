# bamboo_actuator_ros2

## インストール・実行

1. BambooActuatorを接続します。Linuxの接続設定は、Pythonライブラリ側の [udev設定](../../python/README.md#udev設定linux--ubuntudebian) を参照してください。
2. ROS2実行環境で、Pythonライブラリをインストールします。
   `python3 -m pip install /path/to/bamboo_actuator/python`
3. ROS2ワークスペースの `src/` に `bamboo_actuator_ros2` のフォルダを配置し、ビルドを実行します。
4. ROS2ワークスペースで `colcon build --packages-select bamboo_actuator_ros2` を実行し、
   `source install/setup.bash` で読み込みます。
5. `ros2 run bamboo_actuator_ros2 bamboo_actuator_node` を実行します。

## 受信トピック
| 既定トピック | 型 | 内容 |
| --- | --- | --- |
| `/bamboo_actuator/stop` | `std_msgs/Bool` | trueで停止し、待機中の指令も取り消す。falseは無視 |
| `/bamboo_actuator/set_length` | `std_msgs/Int16` | 目標位置 [mm] |
| `/wirelesscontroller` | `unitree_go/WirelessController` | Unitree無線操作 |

## 送信トピック
| `/bamboo_actuator/current_length` | `std_msgs/Int32` | 測定位置 [mm] |
| `/bamboo_actuator/movement_complete` | `std_msgs/Bool` | 指令受付・停止・異常時false、到達通知時trueを1回配信 |
| `/bamboo_actuator/status` | `std_msgs/String` | idle / homing / pending / moving / completed / stopped / error |
| `/bamboo_actuator/error` | `std_msgs/String` | 通信・移動のエラー理由、または無効な入力の説明 |


300 mmへ伸縮：

```sh
ros2 topic pub --once /bamboo_actuator/set_length std_msgs/msg/Int16 "{data: 300}"
```

停止指令の例：

```sh
ros2 topic pub --once /bamboo_actuator/stop std_msgs/msg/Bool "{data: true}"
```

`/bamboo_actuator/status` の各ステータス：

| ステータス | 意味 |
| --- | --- |
| `idle` | 指令待ち |
| `homing` | 本体の原点復帰完了を確認中 |
| `pending` | 移動指令を受け付け、本体への送信待ち |
| `moving` | 移動指令を送信し、完了通知を待機中 |
| `completed` | 本体から移動完了通知を受信済み |
| `stopped` | 停止指令を処理し、待機中の移動指令を取り消した状態 |
| `error` | 接続・通信・移動のエラー、またはタイムアウトが発生 |

## 主なパラメータ

| 名前 | 既定値 | 用途 |
| --- | --- | --- |
| `serial_device` | `/dev/bamboo_actuator` | シリアルポート |
| `baud_rate` | 115200 | 通信速度 |
| `max_length` | 2700 | 許容最大位置 [mm]、0〜4000で設定 |
| `movement_timeout` | 120.0 | 移動完了待ち [秒] |
| `initialization_timeout` | 60.0 | 接続後の原点復帰待ち [秒] |
| `serial_response_timeout` | 0.2 | 1回の問い合わせ応答待ち [秒] |
| `stop_topic` | `/bamboo_actuator/stop` | 停止指令トピック |
| `set_length_topic` | `/bamboo_actuator/set_length` | 指令トピック |
| `completion_topic` | `/bamboo_actuator/movement_complete` | 完了トピック |
| `length_topic` | `/bamboo_actuator/current_length` | 位置トピック |
| `status_topic` | `/bamboo_actuator/status` | 状態トピック |
| `error_topic` | `/bamboo_actuator/error` | エラートピック |
