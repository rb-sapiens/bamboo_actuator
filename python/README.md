# bamboo_actuator

BambooActuatorとシリアル通信するPythonライブラリです。
移動完了通知に対応した本体で使用します。

## インストール

```sh
python3 -m pip install .
```

ROS2で利用する場合は、ROS2ノードを実行するPython環境へインストールしてください。

## udev設定（Linux / Ubuntu・Debian）

接続先を `/dev/bamboo_actuator` に固定します。ROS2ノードもこの名前を既定で使用します。
udevは必須ではなく、実際のポート名を直接指定することもできます。

用意済みの [bamboo_actuator.rules](bamboo_actuator.rules) をコピーして使用します。ファイルの編集は不要です。

1. この `python/` ディレクトリ内で、ルールをコピーして再読み込みします。

   ```sh
   sudo cp bamboo_actuator.rules /etc/udev/rules.d/99-bamboo-actuator.rules
   sudo udevadm control --reload-rules
   ```

2. 本体のUSBを抜き差しし、接続先を確認します。

   ```sh
   readlink -f /dev/bamboo_actuator
   ls -lL /dev/bamboo_actuator
   ```

   接続先が表示されれば設定完了です。付属ルールで読み書き権限を設定するため、グループ追加は不要です。

macOS・Windowsではudevを使いません。`/dev/bamboo_actuator`の部分を、`/dev/cu.usbmodem...` や `COM3` など、実際のポート名で指定します。

## 基本的な使い方

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

## APIと戻り値

| API | 正常時 | エラー時 |
| --- | --- | --- |
| `set_length(length)` | `True`: 指令を送信した | `None` |
| `get_length()` | 現在位置の整数 [mm] | `None` |
| `initialized()` | `True`: 原点復帰済み、`False`: 未完了 | `None` |
| `poll_completion()` | `True`: 到達通知を1回取得、`False`: 新しい通知なし | `None` |
| `wait_until_complete(timeout=None)` | `True`: 到達 | `None` |
| `stop()` / `reset()` / `close()` | `True`: 書き込み・クローズ成功 | `None` |

- 同時に扱う移動は1件です。移動中に次の `set_length()` を呼ぶと `None`（busy）です。置き換える場合は `stop()` を呼んでから再指令します。
- 終了時は `stop()` と `close()` を呼び出してください。

## 通信仕様

コマンドは `;` 終端、応答は改行終端、115200 baudです。

| コマンド | 応答 |
| --- | --- |
| `set:200;` | 到達時 `success`、失敗時 `error:理由` |
| `set:0;` | 原点判定時 `success` |
| `get;` | `length:整数` |
| `initialized;` | `true` / `false` |
| `stop;` | 実行中のsetを中断した場合 `error:stopped` |
| `reset;` | 再起動 |

エラー理由: `invalid_target`、`not_initialized`、`stalled`、`stopped`、`interrupted`。
