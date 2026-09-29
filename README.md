# BambooActuator

BambooActuatorを操作するPython通信ライブラリとROSドライバです。

```text
python/bamboo_actuator/    Python通信ライブラリ
ros2/bamboo_actuator_ros2/ ROS2ノード
ros1/                     旧ROS1パッケージ（非推奨）
```

ROS1/ROS2で使用する場合は、事前にpythonライブラリをインストールする必要があります。

## Pythonライブラリ

リポジトリ直下で実行します。

```sh
python3 -m pip install ./python
```

実行例：

```python
import time
from bamboo_actuator import BambooActuator

ba = BambooActuator("/dev/bamboo_actuator", 115200)
try:
    deadline = time.monotonic() + 60
    while ba.initialized() is not True:
        if time.monotonic() >= deadline:
            raise RuntimeError(ba.last_error or "initialization timeout")
        time.sleep(0.5)

    if ba.set_length(200) is None:
        raise RuntimeError(ba.last_error)
    if ba.wait_until_complete(timeout=120) is None:
        raise RuntimeError(ba.last_error)

    length = ba.get_length()
    if length is None:
        print("通信失敗:", ba.last_error)
    else:
        print("位置 [mm]:", length)
finally:
    ba.stop()
    ba.close()
```

詳細は [PythonライブラリのREADME](python/README.md) を参照してください。

## ROS2

先にROS2で使うPython環境へ `./python` をインストールします。
ROS2ワークスペースの `src/` に `bamboo_actuator_ros2` のフォルダを配置し、ビルドを実行します。

```sh
colcon build --packages-select bamboo_actuator_ros2
source install/setup.bash
ros2 run bamboo_actuator_ros2 bamboo_actuator_node
```

詳細は [ROS2の説明](ros2/bamboo_actuator_ros2/README.md) を参照してください。

## ROS1

ROS1パッケージは `ros1/` にあります。
ROS1の依存ライブラリ・起動方法は [ROS1の説明](ros1/README.md) を参照してください。
