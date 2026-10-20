(function () {
  var ui = document.getElementById("home").dataset;
  var LINES = JSON.parse(ui.lines);
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
    hint.textContent = ui.hintClick;
  }

  // Share links use the page's own address, so they work wherever it is hosted.
  var url = location.href.split("#")[0], msg = ui.shareMessage;
  var q = encodeURIComponent;
  var set = function (id, href) { var el = document.getElementById(id); if (el) el.href = href; };
  set("share-bsky", "https://bsky.app/intent/compose?text=" + q(msg + " " + url));
  set("share-x", "https://twitter.com/intent/tweet?text=" + q(msg) + "&url=" + q(url));
  set("share-reddit", "https://www.reddit.com/submit?url=" + q(url) + "&title=" + q(msg));
  document.getElementById("share-copy").addEventListener("click", function (e) {
    var btn = e.currentTarget;
    function done(ok) { btn.textContent = ok ? ui.copied : url; setTimeout(function () { btn.textContent = ui.copy; }, 1600); }
    try { navigator.clipboard.writeText(url).then(function () { done(true); }, function () { done(false); }); }
    catch (err) { done(false); }
  });
})();
