---
title: 設定ファイルでジェスチャーを編集する
sidebar:
  order: 6
description: config.toml でジェスチャーをステップとして書き、送る内容を選び、ジェスチャーを組み合わせます。
---

ジェスチャーのウィンドウは、`config.toml` に書かれているものと同じ設定を編集します。ジェスチャーをコピーしたい場合、たくさんのジェスチャーを追加したい場合、[コマンドラインのオプション](https://github.com/lulalala/eyeokuri/blob/master/docs/command-line.md)を使う場合は、ファイルを直接編集してください。インストールしたアプリは、このファイルを `%APPDATA%\eyeokuri\config.toml` に保存します。すべての項目は [`config.example.toml`](https://github.com/lulalala/eyeokuri/blob/master/config.example.toml) に載っています。

設定ファイルは `version = 1` で始まる必要があります。この行がないファイルは古い形式で、アイ送りは読み込みを拒否します。`config.example.toml` からやり直してください。

## ジェスチャーを書く

各ジェスチャーは、ステップの並びです。ステップは、1 つの信号を時間に沿って表したグラフ上のボックスで、信号がボックスに入った瞬間に成立します。信号の `eyes`、`wink`、`pitch`、`yaw` については、[グラフを読む](../edit-a-gesture/#グラフを読む)を参照してください。

組み込みのまばたきは、「eyes が 60% より下になり、その 0.1～1 秒後に eyes が 70% より上になる」というジェスチャーです。

```toml
[gestures.blink]
steps = [
  { signal = "eyes", below_ratio = 0.6 },
  { signal = "eyes", above_ratio = 0.7, after_min_s = 0.1, after_max_s = 1.0 },
]
guards = [
  { signal = "yaw", above_deg = -20.0, below_deg = 20.0 },
  { signal = "pitch", above_deg = -10.0, below_deg = 10.0 },
]
cooldown_s = 1.0
output = "enter"
```

各ステップは自分のボックスとタイミングを持つので、1 つのステップを変えても他のステップには影響しません。

| 項目 | 意味 |
| --- | --- |
| `above_ratio`、`below_ratio` | `eyes` と `wink` のボックスです。片方を省くと、その側が開いたボックスになります。 |
| `above_deg`、`below_deg` | `pitch` と `yaw` のボックスです。 |
| `after_min_s`、`after_max_s` | 前のステップから許される時間です。0 は制限なしです。 |
| `hold_s` | ステップが成立するまで、信号がボックスの中にとどまる時間です。たとえば、1 秒間左を向いたときに反応させる場合に使います。 |

ジェスチャーには、次の項目もあります。

| 項目 | 意味 |
| --- | --- |
| `guards` | 頭がその中にとどまる必要がある、`pitch` または `yaw` のボックスです。 |
| `any_order` | ステップをどちらの順序でも成立させます。首を振るジェスチャーが使っています。 |
| `within_s` | 最初のステップから最後のステップまでに許される時間です。 |
| `cooldown_s` | ジェスチャーが反応したあと、再び反応できない時間です。 |
| `enabled` | ジェスチャーをオンまたはオフにします。 |
| `output` | ジェスチャーが送る内容です。 |

これらの名前は、[ジェスチャーのウィンドウ](../edit-a-gesture/#範囲を変更する)の列や行にも表示されます。

## 目をそらしているときに反応しないようにする

ガードは、`pitch` または `yaw` 上のボックスです。頭がどれかのガードの外にある間は、ジェスチャーを開始できず、進行中のジェスチャーはキャンセルされます。ログには理由が表示されます。たとえば `blink: canceled (head yaw +25° outside its limit)` です。頭を回している間に始まった目の閉じは、頭を戻したあとでは数えられません。

初期設定では、頭が普段の姿勢から左右に 20° 以内、上下に 10° 以内にあるときだけ、まばたきが数えられます。10° はうなずきの 12° の内側なので、うなずいたときの目の動きがまばたきとして数えられることはありません。どの頭の角度でもまばたきを数えたい場合は、`guards = []` に設定してください。ジェスチャーのウィンドウでは、**頭が次の範囲内にあるときだけ** の行でガードを編集できます。

## ジェスチャーが送る内容を選ぶ

`output` には、次のいずれかを指定します。

- キー：`a`～`z`、`0`～`9`、`f1`～`f24`、`enter`、`space`、`tab`、`escape`、`backspace`、`delete`、`insert`、`home`、`end`、`page_up`、`page_down`、`up`、`down`、`left`、`right`。
- 1 つ以上の修飾キー（`ctrl`、`shift`、`alt`、`win`）と `+` でつないだキー。たとえば `ctrl+s` や `shift+tab` です。
- マウス入力：`left_click`、`right_click`、`wheel_down`。
- `app:toggle_pause`：アイ送りを一時停止または再開します。
- `""`：何も送りません。

## ジェスチャーを組み合わせる

新しい名前で、自分のジェスチャーを追加できます。ステップには別のジェスチャーを指定することもでき、そのジェスチャーが反応したときに成立します。次のジェスチャーは、まばたきしてから 1.5 秒以内に下向きにうなずくと、`space` を送ります。

```toml
[gestures.nod_down]
enabled = true
output = ""           # うなずきだけでは何も送らない

[gestures.blink_then_nod]
steps = [{ gesture = "blink" }, { gesture = "nod_down", after_max_s = 1.5 }]
output = "space"
```

1 つの動きが複数のジェスチャーに一致した場合は、それぞれが反応します。この例では、まばたきのあとにうなずくと `blink` も反応するので、`Enter` も送られます。
