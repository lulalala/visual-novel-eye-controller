// Homepage text per locale. Add a locale here, then a page in src/pages/<locale>/index.astro.
export interface HomeText {
  lang: string;
  langName: string;
  title: string;
  description: string;
  ogDescription: string;
  keywords: string;
  nav: { download: string; docs: string; github: string; language: string };
  heroLine1: string;
  heroLine2: string;
  sub: string;
  cta: string;
  meta: string[];
  demoLabel: string;
  eyeLabel: string;
  dialogLabel: string;
  speaker: string;
  hintBlink: string;
  hintClick: string;
  enterSent: string;
  lines: string[];
  share: { copy: string; copied: string; message: string };
  gestures: {
    kicker: string;
    title: string;
    text: string;
    shotAlt: string;
  };
  start: { title: string; steps: { title: string; text: string }[]; button: string; trust: string[] };
  pass: { title: string; star: string; request: string };
  footer: string;
  footerReleases: string;
  footerCredits: string;
}

export const home: Record<string, HomeText> = {
  en: {
    lang: "en",
    langName: "English",
    title: "eyeokuri: Blink. Next line.",
    description: "Read your visual novel hands‑free. eyeokuri turns a blink into the Enter key.",
    ogDescription:
      "Read your visual novel hands-free. Blink to advance the text, shake your head to pause. Free, open source, and nothing leaves your PC.",
    keywords: "visual novel, hands-free, blink to advance, webcam, eye control, accessibility, auto advance",
    nav: { download: "Download", docs: "Docs", github: "GitHub", language: "Language" },
    heroLine1: "Blink.",
    heroLine2: "Next line.",
    sub: "Read your visual novel hands-free. eyeokuri turns a blink into the Enter key.",
    cta: "Download",
    meta: ["Free", "Open source", "About 65 MB"],
    demoLabel: "Interactive demo of eyeokuri in a visual novel",
    eyeLabel: "An anime eye that blinks",
    dialogLabel: "Advance the dialogue (blink, click, or press Space)",
    speaker: "eyeokuri",
    hintBlink: "Blink to continue",
    hintClick: "Click to continue",
    enterSent: "Enter ⏎<br>sent",
    lines: [
      "H-hands full of snacks? Good. It's not like I wanted you to need them or anything!",
      "Carpal tunnel? Tch, rest your hands. I-I'm not worried!",
      "I watch your webcam. When you blink, I press Enter. Don't read into it, idiot!",
      "Need a break? Shake your head. I'll wait. B-but only because I'm bored!",
      "Everything stays on your PC. I never save a frame. W-what, you thought I'd peek at you?!",
      "Hmph. Ready? Blink once, and the story is yours. Just don't make me say it twice!",
    ],
    share: {
      copy: "Copy link",
      copied: "Copied",
      message: "Blink. Next line. Read your visual novel hands-free with eyeokuri.",
    },
    gestures: {
      kicker: "gesture → key",
      title: "Your face is the controller",
      text: "eyeokuri watches your webcam and presses keys for you. Blink to read on, and shake your head when you need a break.",
      shotAlt: "The eyeokuri window: a list of gestures with their keys and on switches, and the start of the log",
    },
    start: {
      title: "Your hands are free now",
      steps: [
        { title: "Download", text: "Free for Windows, about 65 MB. Any webcam works, even an Android phone as a webcam." },
        {
          title: "Run it",
          text: "The app is not signed, so Windows might warn about an unknown publisher. Select <b>More info</b>, then <b>Run anyway</b>.",
        },
        { title: "Adjust", text: "A wizard is available to learn your blink, or you can customize new gestures manually." },
      ],
      button: "Download for Windows",
      trust: ["Camera frames never leave your PC", "Free and open source", "Online once, for a 4 MB face model"],
    },
    pass: {
      title: "Spread the word",
      star: "★ Star on GitHub",
      request: "Request a gesture →",
    },
    footer: "eyeokuri · open source · made for people who read a lot",
    footerReleases: "All releases",
    footerCredits: "Credits",
  },
  "zh-tw": {
    lang: "zh-TW",
    langName: "繁體中文",
    title: "eyeokuri：眨眼，下一句。",
    description: "不用動手也能讀視覺小說。eyeokuri 把你的眨眼變成 Enter 鍵。",
    ogDescription:
      "不用動手也能讀視覺小說：眨眼跳下一句，搖頭暫停。免費、開源，資料完全不會離開你的電腦。",
    keywords: "視覺小說, galgame, 免手動, 眨眼翻頁, 視訊鏡頭, 眼部控制, 無障礙, 自動播放",
    nav: { download: "下載", docs: "使用說明", github: "GitHub", language: "語言" },
    heroLine1: "眨眼，",
    heroLine2: "下一句。",
    sub: "躺著也能推 galgame。eyeokuri 把眨眼變成 Enter 鍵，雙手從此解放。",
    cta: "下載",
    meta: ["免費", "開源", "約 65 MB"],
    demoLabel: "eyeokuri 在視覺小說中的互動示範",
    eyeLabel: "一隻會眨眼的動漫風眼睛",
    dialogLabel: "推進對話（眨眼、點擊或按空白鍵）",
    speaker: "eyeokuri",
    hintBlink: "眨眼繼續",
    hintClick: "點擊繼續",
    enterSent: "Enter ⏎<br>已送出",
    lines: [
      "手……手上拿滿零食了？很好。我才不是想讓你依賴我呢！",
      "滑鼠手又犯了？嘖，手給我好好休息。我……我才沒有擔心你呢！",
      "我會一直盯著你的鏡頭，你一眨眼，我就幫你按 Enter。別……別想太多喔，笨蛋！",
      "想休息？搖搖頭就好，我會等你。只……只是因為我很閒而已！",
      "所有東西都留在你的電腦裡，我一格畫面都不會存。蛤？你該不會以為我會偷看你吧！",
      "哼，準備好了嗎？眨一下眼，故事就交給你了。這種話我可不說第二次喔！",
    ],
    share: {
      copy: "複製連結",
      copied: "已複製",
      message: "眨眼，下一句。用 eyeokuri，雙手不碰鍵盤也能讀視覺小說。",
    },
    gestures: {
      kicker: "動作 → 按鍵",
      title: "你的臉就是手把",
      text: "eyeokuri 透過視訊鏡頭看著你，替你按下按鍵。眨眼繼續讀，想休息就搖搖頭。",
      shotAlt: "eyeokuri 視窗：動作清單，列出各動作對應的按鍵與開關，下方是記錄的開頭",
    },
    start: {
      title: "你的雙手，自由了",
      steps: [
        { title: "下載", text: "Windows 版免費，約 65 MB。任何視訊鏡頭都能用，連 Android 手機當鏡頭也行。" },
        {
          title: "執行",
          text: "這個程式沒有數位簽章，所以 Windows 可能會警告「不明的發行者」。選擇<b>其他資訊</b>，再按<b>仍要執行</b>。",
        },
        { title: "調整", text: "內建精靈可以學習你的眨眼方式，你也可以手動自訂新動作。" },
      ],
      button: "下載 Windows 版",
      trust: ["鏡頭畫面絕不離開你的電腦", "免費且開源", "只連網一次，下載 4 MB 的臉部模型"],
    },
    pass: {
      title: "好東西就是要跟好朋友分享",
      star: "★ 在 GitHub 上給星星",
      request: "許願新動作 →",
    },
    footer: "開源軟體 eyeokuri，獻給文字量爆表的你",
    footerReleases: "所有版本",
    footerCredits: "致謝",
  },
};
