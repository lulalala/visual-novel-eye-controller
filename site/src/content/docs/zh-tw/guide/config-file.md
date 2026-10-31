---
title: 在設定檔中編輯動作
sidebar:
  order: 6
description: 在 config.toml 把動作寫成步驟，選擇它送出什麼，並把動作組合起來。
---

動作視窗編輯的，就是 `config.toml` 裡的同一組設定。如果你想複製動作、一次新增很多動作，或要搭配[命令列選項](https://github.com/lulalala/eyeokuri/blob/master/docs/command-line.md)，可以直接編輯這個檔案。安裝版會把檔案放在 `%APPDATA%\eyeokuri\config.toml`。[`config.example.toml`](https://github.com/lulalala/eyeokuri/blob/master/config.example.toml) 列出了每個欄位。

設定檔必須以 `version = 1` 開頭。沒有這一行的檔案使用舊的格式，eyeokuri 會拒絕載入。請從 `config.example.toml` 重新開始。

## 撰寫動作

每個動作都是一串步驟。步驟是畫在某個訊號隨時間變化的圖上的一個方框，訊號進入方框的那一刻，這個步驟就算達成。關於 `eyes`、`wink`、`pitch`、`yaw` 和 `roll` 這幾個訊號，請看[看懂圖表](../edit-a-gesture/#看懂圖表)。

內建的眨眼是「eyes 低於 60%，然後在 0.1 秒到 1 秒之後 eyes 高於 70%」：

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

每個步驟都有自己的方框和時間設定，所以你可以只改一個步驟，不影響其他步驟：

| 欄位 | 意義 |
| --- | --- |
| `above_ratio`、`below_ratio` | `eyes` 和 `wink` 的方框。省略其中一個，那一側就是開放的。 |
| `above_deg`、`below_deg` | `pitch`、`yaw` 和 `roll` 的方框。 |
| `after_min_s`、`after_max_s` | 距離上一個步驟允許的時間。0 代表不限制。 |
| `hold_s` | 訊號必須在方框內停留多久，這個步驟才算數，例如看向左邊 1 秒才觸發。 |

動作還有這些欄位：

| 欄位 | 意義 |
| --- | --- |
| `guards` | `pitch` 或 `yaw` 上的方框，頭部必須待在裡面。 |
| `any_order` | 讓步驟可以用任一種順序發生。搖頭動作就使用它。 |
| `within_s` | 從第一個步驟到最後一個步驟允許的時間。 |
| `cooldown_s` | 動作觸發之後，在這段時間內不能再次觸發。 |
| `enabled` | 開啟或關閉動作。 |
| `output` | 動作送出什麼。 |
| `output_mode` | `press`（預設）送出一次輸出；`while` 會按住輸出，直到動作結束。 |

這些名稱也會出現在[動作視窗](../edit-a-gesture/#變更範圍)的欄和列。

## 避免在你轉頭看別處時觸發

限制是 `pitch` 或 `yaw` 上的方框。只要你的頭部在任何一個限制之外，動作就無法開始，進行到一半的動作也會被取消。記錄會說明原因，例如 `blink: canceled (head yaw +25° outside its limit)`。在轉頭時開始的閉眼，等你轉回來之後也不會算數。

預設情況下，只有當你的頭部在左右方向離平常姿勢 20° 以內、上下方向 10° 以內時，眨眼才會算數。10° 在點頭的 12° 之內，所以點頭時的眼睛動作不會同時被算成眨眼。如果要讓眨眼在任何頭部角度都算數，請設定 `guards = []`。在動作視窗中，**只在頭部維持在這個範圍內時** 這幾列可以編輯這些限制。

## 選擇動作送出什麼

`output` 可以是以下其中一種：

- 按鍵：`a`–`z`、`0`–`9`、`f1`–`f24`、`enter`、`space`、`tab`、`escape`、`backspace`、`delete`、`insert`、`home`、`end`、`page_up`、`page_down`、`up`、`down`、`left` 或 `right`。
- 加上一個或多個修飾鍵（`ctrl`、`shift`、`alt`、`win`）的按鍵，用 `+` 連接，例如 `ctrl+s` 或 `shift+tab`。
- 滑鼠輸入：`mouse_left_click`、`mouse_right_click` 或 `mouse_wheel_down`。
- `app_pause_toggle`：暫停或繼續 eyeokuri。
- `""`：不送出任何東西。

`output_mode` 決定輸出怎麼送出：`press`（預設）送出一次，`while` 會按住直到動作結束。每一種的行為，以及 eyeokuri 什麼時候放開，請見[按住按鍵](../main-window/#按住按鍵)。下面這個動作會在你閉著左眼時按住 `ctrl`（許多遊戲用它跳過文字）：

```toml
[gestures.skip]
steps = [{ signal = "wink", above_ratio = 0.25, hold_s = 0.3 }]
output = "ctrl"
output_mode = "while"   # 睜開左眼時放開
```

## 組合動作

你可以用新的名稱加入自己的動作。步驟也可以是另一個動作，在那個動作觸發時算數。下面這個動作會在你眨眼之後 1.5 秒內往下點頭時，送出 `space`：

```toml
[gestures.nod_down]
enabled = true
output = ""           # 單獨點頭時不送出任何東西

[gestures.blink_then_nod]
steps = [{ gesture = "blink" }, { gesture = "nod_down", after_max_s = 1.5 }]
output = "space"
```

當同一個動作符合多個動作時，每一個都會觸發。在這個例子中，眨眼之後點頭也會觸發 `blink`，所以也會送出 `Enter`。
