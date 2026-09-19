/* Draws the decorative code squares in the "Reading with the book" section.
   These are not scannable and are not meant to be — the real codes are
   generated from moments.json when the book goes to print. This only has to
   look like a code from across a room. Deterministic, so it never flickers
   between page loads. */
(function () {
  function fill(grid) {
    var n = 21;
    var seed = parseInt(grid.dataset.seed || '7', 10) || 7;
    var s = seed;
    function rnd() {            // mulberry-ish; stable for a given seed
      s = (s * 1664525 + 1013904223) % 4294967296;
      return s / 4294967296;
    }
    function finder(x, y) {     // the three big corner squares
      var inX = (x < 7 && y < 7) || (x > n - 8 && y < 7) || (x < 7 && y > n - 8);
      if (!inX) return null;
      var cx = x < 7 ? x : x - (n - 7);
      var cy = y < 7 ? y : y - (n - 7);
      var ring = Math.max(Math.abs(cx - 3), Math.abs(cy - 3));
      return ring === 1 || ring === 3 ? false : true;
    }
    var cells = '';
    for (var y = 0; y < n; y++) {
      for (var x = 0; x < n; x++) {
        var f = finder(x, y);
        var on = f === null ? rnd() > 0.47 : f;
        cells += on ? '<i></i>' : '<i class="o"></i>';
      }
    }
    grid.innerHTML = cells;
  }
  document.querySelectorAll('.qrgrid').forEach(fill);
})();
