(function () {
  var LINES = [
    "H-hands full of snacks? Good. It's not like I wanted you to need them or anything!",
    "I watch your webcam. When you blink, I press Enter. Don't read into it, idiot!",
    "Need a break? Shake your head. I'll wait. B-but only because I'm bored!",
    "Everything stays on your PC. I never save a frame. W-what, you thought I'd peek at you?!",
    "Hmph. Ready? Blink once, and the story is yours. Just don't make me say it twice!"
  ];
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var svg = document.querySelector(".eye svg");
  var lineEl = document.getElementById("line");
  var dialog = document.getElementById("dialog");
  var hint = document.getElementById("hint");
  var key = document.getElementById("key");
  var dots = document.getElementById("dots");
  var idx = 0, typer = null, keyTimer = null;
  var BLINK_AT = 3.2, CYCLE = 4; // seconds into the logo's 4 s loop when the lid is shut

  LINES.forEach(function () { dots.appendChild(document.createElement("b")); });

  function show(i, instant) {
    idx = i;
    clearInterval(typer);
    var text = LINES[i];
    Array.prototype.forEach.call(dots.children, function (d, n) { d.className = n === i ? "on" : ""; });
    if (instant || reduce) { lineEl.textContent = text; return; }
    var n = 0; lineEl.textContent = "";
    typer = setInterval(function () {
      n += 1; lineEl.textContent = text.slice(0, n);
      if (n >= text.length) clearInterval(typer);
    }, 24);
  }

  function flash() {
    key.classList.add("on"); dialog.classList.add("pulse");
    clearTimeout(keyTimer);
    keyTimer = setTimeout(function () { key.classList.remove("on"); dialog.classList.remove("pulse"); }, 900);
  }

  function advance(fromBlink) {
    if (fromBlink) flash();
    show((idx + 1) % LINES.length);
  }

  dialog.addEventListener("click", function (e) {
    if (e.target.closest("a")) return;
    advance(false);
  });
  dialog.addEventListener("keydown", function (e) {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); advance(false); }
  });

  show(0, false);

  // Advance on the logo's own blink so the demo shows cause and effect.
  if (svg && svg.getCurrentTime && !reduce) {
    var prev = svg.getCurrentTime() % CYCLE;
    (function tick() {
      var now = svg.getCurrentTime() % CYCLE;
      if (prev < BLINK_AT && now >= BLINK_AT) advance(true);
      prev = now;
      requestAnimationFrame(tick);
    })();
  } else if (svg && svg.pauseAnimations) {
    svg.pauseAnimations();
    hint.textContent = "Click to continue";
  }

  // Share links use the page's own address, so they work wherever it is hosted.
  var url = location.href.split("#")[0], msg = "Blink. Next line. Read your visual novel hands-free with eyeokuri.";
  var q = encodeURIComponent;
  var set = function (id, href) { var el = document.getElementById(id); if (el) el.href = href; };
  set("share-bsky", "https://bsky.app/intent/compose?text=" + q(msg + " " + url));
  set("share-x", "https://twitter.com/intent/tweet?text=" + q(msg) + "&url=" + q(url));
  set("share-reddit", "https://www.reddit.com/submit?url=" + q(url) + "&title=" + q(msg));
  document.getElementById("share-copy").addEventListener("click", function (e) {
    var btn = e.currentTarget;
    function done(ok) { btn.textContent = ok ? "Copied" : url; setTimeout(function () { btn.textContent = "Copy link"; }, 1600); }
    try { navigator.clipboard.writeText(url).then(function () { done(true); }, function () { done(false); }); }
    catch (err) { done(false); }
  });

  document.getElementById("copy").addEventListener("click", function (e) {
    var btn = e.currentTarget;
    var text = document.getElementById("cmd").textContent.replace(/^Copy/, "").trim();
    function done(ok) { btn.textContent = ok ? "Copied" : "Select and copy"; setTimeout(function () { btn.textContent = "Copy"; }, 1600); }
    try { navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); }); }
    catch (err) { done(false); }
  });
})();
