# bsactuator_ros

RoboSapiens が開発する Bambooshoot Actuator とやりとりをするための ROS パッケージです。

## 事前準備

Python 3.8以降で動作するROS1環境と、このリポジトリの `bamboo_actuator >= 0.3.0` を使用します。
ROS1ノードを実行するPython環境へインストールしてください（リポジトリ直下で実行）。

```sh
python3 -m pip install ./python
```

USB接続の設定は、Pythonライブラリ側の [udev設定](../python/README.md#udev設定linux--ubuntudebian) を参照してください。

## Launch ファイルの実行

```
roslaunch bsactuator_ros bsactuator.launch
```


## Subscribers

#### /set_length

伸縮長さを指定する

ex.

```
rostopic pub -1 /set_length std_msgs/Int16 300
```

#### /bamboo_actuator/stop

`std_msgs/Bool` の `true` で停止します。`false` は無視します。

```sh
rostopic pub -1 /bamboo_actuator/stop std_msgs/Bool "{data: true}"
```

互換用に従来の `/stop`（`std_msgs/String`、`data: 'true'`）も利用できます。
停止した移動について、到達ステータスは発行しません。

## Publishers

#### /bamboo_actuator/length

現在の長さ[mm]

#### /bamboo_actuator/status

本体から移動完了通知を受信した時に発行する `actionlib_msgs/GoalStatus`（status=3）。
