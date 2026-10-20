// Homepage text per locale. Add a locale here, then a page in src/pages/<locale>/index.astro.
export interface HomeText {
  lang: string;
  title: string;
  description: string;
  ogDescription: string;
  keywords: string;
  nav: { download: string; docs: string; github: string };
  heroLine1: string;
  heroLine2: string;
  sub: string;
  cta: string;
  meta: string;
  demoLabel: string;
  eyeLabel: string;
  dialogLabel: string;
  speaker: string;
  hintBlink: string;
  hintClick: string;
  enterSent: string;
  lines: string[];
  share: { prompt: string; copy: string; copied: string; message: string };
  facts: { glyph: string; title: string; text: string }[];
  install: { title: string; text: string; button: string; small: string };
  keep: { title: string; text: string; star: string; request: string };
  footer: string;
}

export const home: Record<string, HomeText> = {
  en: {
    lang: "en",
    title: "eyeokuri: Blink. Next line.",
    description: "Read your visual novel hands‑free. eyeokuri turns a blink into the Enter key.",
    ogDescription:
      "Read your visual novel hands-free. Blink to advance the text, shake your head to pause. Free, open source, and nothing leaves your PC.",
    keywords: "visual novel, hands-free, blink to advance, webcam, eye control, accessibility, auto advance",
    nav: { download: "Download", docs: "Docs", github: "GitHub" },
    heroLine1: "Blink.",
    heroLine2: "Next line.",
    sub: "Read your visual novel hands-free. eyeokuri turns a blink into the Enter key.",
    cta: "Download",
    meta: "Free · open source · about 65 MB",
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
      prompt: "Know a VN reader?",
      copy: "Copy link",
      copied: "Copied",
      message: "Blink. Next line. Read your visual novel hands-free with eyeokuri.",
    },
    facts: [
      {
        glyph: "blink → Enter",
        title: "Blink to advance",
        text: "A blink sends Enter, space or click to your game.",
      },
      {
        glyph: "shake → pause",
        title: "Shake to pause",
        text: "Shake your head to pause, and shake again to unpause.",
      },
      {
        glyph: "frames → nowhere",
        title: "Stays on your PC",
        text: "Camera frames are read in memory. They are never saved or sent anywhere.",
      },
    ],
    install: {
      title: "Your hands are free now",
      text: "Works with any webcam (e.g. Android phone as webcam). A wizard learns your blink from a few practice takes.",
      button: "Download for Windows",
      small:
        "The first run downloads a 4 MB face model, so be online once. Windows might warn about an unknown publisher because the app is not signed. Select <b>More info</b>, then <b>Run anyway</b>.",
    },
    keep: {
      title: "Make it yours",
      text: "The gesture wizard learns your blink from a few practice takes. You can also turn on nod up and nod down for the arrow keys, or send space, a click or a scroll instead of Enter.",
      star: "★ Star to follow new gestures",
      request: "Request a gesture",
    },
    footer: "eyeokuri · open source · made for people who read a lot",
  },
};
