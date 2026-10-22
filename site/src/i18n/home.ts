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
  pass: { title: string; text: string; star: string; request: string };
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
};
