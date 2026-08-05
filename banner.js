/* TODAY IN SXM — shared banner client.
   Reads today.json (built daily by tools/build_today.py) plus live weather and
   marine data. Handles only what needs the current clock. Renders nothing for
   any state whose copy has not been written. */
(function () {
  'use strict';
  var LAT = 18.03, LON = -63.05;
  var $ = function (id) { return document.getElementById(id); };
  if (!$('wx-advice')) return;

  var getJSON = function (url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(r.status); return r.json();
    });
  };
  var mins = function (hhmm) { var p = hhmm.split(':'); return +p[0] * 60 + +p[1]; };
  var nowMins = function () { var d = new Date(); return d.getHours() * 60 + d.getMinutes(); };
  var compass = function (deg) {
    return ['N','NE','E','SE','S','SW','W','NW'][Math.round((deg % 360) / 45) % 8];
  };
  var list = function (a) {
    return a.length < 2 ? (a[0] || '') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1];
  };
  var MONTHS = ['January','February','March','April','May','June',
                'July','August','September','October','November','December'];

  /* ---- ported from sxm_logic.py; kept identical on purpose ---- */
  function inArc(deg, arc) {
    var lo = arc[0], hi = arc[1]; deg = ((deg % 360) + 360) % 360;
    return lo > hi ? (deg >= lo || deg <= hi) : (deg >= lo && deg <= hi);
  }
  function swellState(h, dir, per, cfg, windKt) {
    if (h == null || dir == null) return 'SWELL_DATA_STALE';
    per = per || 0;
    if (inArc(dir, cfg.nw_arc)) {
      if (h >= cfg.severe.height || per >= cfg.severe.period) return 'SWELL_NORTH_WEST_DANGEROUS';
      if (h >= cfg.alert.height  && per >= cfg.alert.period)  return 'SWELL_NORTH_WEST_ROUGH';
      if (h >= cfg.watch.height  && per >= cfg.watch.period)  return 'SWELL_NORTH_WEST_ROUGH';
    }
    if (windKt != null && windKt >= cfg.wind_kt_unpleasant) return 'SWELL_EAST_WINDY';
    if (inArc(dir, cfg.e_arc) && h >= cfg.east_choppy_wave) return 'SWELL_EAST_CHOPPY';
    return 'SWELL_CALM';
  }
  var bridgeTime = null;
  function bridgeSlots(t) {
    var out = [], n = nowMins();
    bridgeTime = null;
    (t.bridges.compound_windows || []).forEach(function (w) {
      if (n >= mins(w.start) && n <= mins(w.end)) out.push(w.key);
    });
    if (out.length) return out;
    // Causeway opens on demand only, so it is not worth warning about.
    var best = null;
    Object.keys(t.bridges.schedule).forEach(function (k) {
      var b = t.bridges.schedule[k];
      if (!b.primary) return;
      b.times.forEach(function (x) {
        var d = mins(x) - n;
        if (d >= 0 && d <= 45 && (!best || d < best.d)) best = { d: d, t: x, key: k };
      });
    });
    if (best) {
      bridgeTime = best.t;
      out.push(best.key === 'sandy_ground' ? 'BRIDGE_SANDY_GROUND' : 'BRIDGE_SIMPSON_BAY');
    }
    return out;
  }
  function fmtTime(hhmm) {
    var p = hhmm.split(':'), h = +p[0], ap = h >= 12 ? 'pm' : 'am';
    return ((h % 12) || 12) + ':' + p[1] + ' ' + ap;
  }

  /* ---- grouping: cap per category, never drop a whole subject ---- */
  var GROUPS = [
    { key: 'ROADS',   label: 'ROADS',     max: 3, match: /^(TRAFFIC|ANOMALY|BRIDGE)_/ },
    { key: 'WATER',   label: 'WATER',     max: 1, match: /^SWELL_/ },
    { key: 'BEACHES', label: 'BEACHES',   max: 2, match: /^(SARGASSUM|CROWD)_/ },
    { key: 'WHATSON', label: "WHAT'S ON", max: 2, match: /^(EVENT|CLOSURE|SPECIALS)_/ }
  ];
  var EXCLUSIVE = [
    ['TRAFFIC_EMPTY','TRAFFIC_QUIET','TRAFFIC_NORMAL','TRAFFIC_BUSY','TRAFFIC_CONGESTED',
     'TRAFFIC_GRIDLOCK','TRAFFIC_ZERO_SHIPS_STILL_BUSY','TRAFFIC_DATA_STALE'],
    ['SWELL_NORTH_WEST_DANGEROUS','SWELL_NORTH_WEST_ROUGH','SWELL_EAST_CHOPPY',
     'SWELL_EAST_WINDY','SWELL_CALM','SWELL_DATA_STALE'],
    ['SARGASSUM_LIKELY','SARGASSUM_POSSIBLE','SARGASSUM_UNLIKELY']
  ];
  function group(slots) {
    var seen = {}, uniq = slots.filter(function (s) {
      if (seen[s]) return false; seen[s] = 1; return true;
    });
    return GROUPS.map(function (g) {
      var picked = [];
      uniq.forEach(function (s) {
        if (picked.length >= g.max || !g.match.test(s)) return;
        var clash = EXCLUSIVE.some(function (grp) {
          return grp.indexOf(s) > -1 && picked.some(function (c) { return grp.indexOf(c) > -1; });
        });
        if (!clash) picked.push(s);
      });
      return { label: g.label, key: g.key, slots: picked };
    });
  }

  var CSS =
    '.brow{display:grid;grid-template-columns:64px 1fr;gap:10px;padding:6px 0;border-top:1px solid #EFDCB4}' +
    '.brow:first-child{border-top:0;padding-top:0}' +
    '.bk{font-family:Montserrat,sans-serif;font-weight:700;font-size:8px;letter-spacing:.11em;color:#A6813C;padding-top:3px}' +
    '.bv{font-size:11.5px;color:#7A5410;line-height:1.5;margin:0}' +
    '.bv + .bv{margin-top:5px}' +
    /* area rows are their own grid so wrapped lines stay in the text column */
    '.barea{display:grid;grid-template-columns:78px 1fr;gap:8px;align-items:baseline}' +
    '.barea > span{font-family:Montserrat,sans-serif;font-weight:700;font-size:8px;' +
      'letter-spacing:.09em;color:#B08E48;line-height:1.6}' +
    /* stop "13 mph NE" breaking across three lines */
    '.wx{white-space:nowrap}' +
    '.bfoot{display:flex;align-items:center;justify-content:space-between;' +
      'gap:8px 16px;flex-wrap:wrap;margin-top:8px}' +
    '.bfoot .ext{margin-top:0;align-self:center}' +
    '.bigram{display:inline-flex;align-items:center;gap:6px;margin:0;' +
      'text-decoration:none;width:fit-content}' +
    '.bigram b{font-weight:500;font-size:11.5px;color:#9A5A12}' +
    '.bigram i{display:inline-flex;width:20px;height:20px;border-radius:5px;' +
      'align-items:center;justify-content:center;flex:none;' +
      'background:linear-gradient(45deg,#F9CE34 5%,#EE2A7B 50%,#6228D7 95%)}' +
    '@media(min-width:820px){.brow{grid-template-columns:82px 1fr}.bv{font-size:13px}' +
      '.barea{grid-template-columns:104px 1fr}.barea > span{font-size:8.5px}' +
      '.bigram i{width:22px;height:22px}}';
  var st = document.createElement('style'); st.textContent = CSS;
  document.head.appendChild(st);

  /* ---------------------------- render ---------------------------- */
  var windKt = null;
  function render(t, copy, marine) {
    if ($('wx-date')) {
      $('wx-date').textContent = new Date().toLocaleDateString('en-GB',
        { weekday: 'short', day: 'numeric', month: 'short' });
    }
    var tr = t.traffic;
    if ($('wx-ships')) {
      $('wx-ships').textContent = !tr.ships_known ? '—'
        : tr.ship_count === 0 ? 'No ships'
        : tr.ship_count + (tr.ship_count === 1 ? ' ship' : ' ships');
    }

    var slots = bridgeSlots(t).concat(t.slots || []);
    if (marine) slots.push(swellState(marine.h, marine.dir, marine.per, t.swell_config, windKt));

    var n = nowMins(), cw = t.crowd_window;
    if (['BUSY','CONGESTED','GRIDLOCK'].indexOf(tr.severity) > -1 &&
        n >= mins(cw.start) && n <= mins(cw.end)) slots.push('CROWD_AVOID_LIST');

    var monthName = MONTHS[new Date(t.date + 'T12:00:00').getMonth()];
    var line = function (k) {
      var l = copy.slots[k];
      if (!l) return '';
      return l.replace('{month}', monthName)
              .replace('{time}', bridgeTime ? fmtTime(bridgeTime) : '');
    };

    var shipsLine = '';
    if (tr.ships_known) {
      if (tr.ship_count === 0) shipsLine = copy.ships.none || '';
      else if (copy.ships.some) {
        shipsLine = copy.ships.some
          .replace('{ships}', list(tr.ships.map(function (s) { return s.ship; })))
          .replace('{pax}', tr.cruise_pax.toLocaleString());
      }
    }

    var esc = function (x) {
      return String(x).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    };
    var rows = [], used = [];
    group(slots).forEach(function (g) {
      var parts = g.slots.map(line).filter(Boolean);
      if (g.key === 'ROADS' && shipsLine) parts.unshift(shipsLine);

      var body = '';
      if (g.key === 'WHATSON') {
        var areas = t.specials || {};
        var names = Object.keys(areas);
        if (parts.length) body += '<p class="bv">' + parts.join(' ') + '</p>';
        names.forEach(function (a) {
          body += '<p class="bv barea"><span>' + esc(a) + '</span>' +
                  esc(areas[a].join('. ')) + '</p>';
        });
        if (!body) return;
      } else {
        if (!parts.length) return;                     // silent category disappears
        body = '<p class="bv">' + parts.join(' ') + '</p>';
      }
      used = used.concat(g.slots);
      rows.push('<div class="brow"><div class="bk">' + g.label + '</div><div>' + body + '</div></div>');
    });

    var host = $('wx-advice');
    if (host.tagName === 'P') {                        // divs cannot live inside a <p>
      var div = document.createElement('div');
      div.id = 'wx-advice'; div.className = host.className;
      host.parentNode.replaceChild(div, host);
      host = div;
    }
    host.innerHTML = rows.join('');
    host.setAttribute('data-slots', used.join(','));
    mountFooterRow(host);
  }

  var IG_HTML =
    '<a class="bigram" href="https://www.instagram.com/todayinsxm" target="_blank"' +
    ' rel="noopener" aria-label="Follow Today In SXM on Instagram">' +
    '<b>Follow for daily updates</b><i>' +
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff"' +
    ' stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="2" y="2" width="20" height="20" rx="5.5"/>' +
    '<circle cx="12" cy="12" r="4.2"/>' +
    '<circle cx="17.6" cy="6.4" r="1.15" fill="#fff" stroke="none"/>' +
    '</svg></i></a>';

  /* Sargassum link and Instagram link on one line at the foot of the box.
     They are siblings in every page's HTML, so this is done here once rather
     than editing nine files. Idempotent. */
  function mountFooterRow(host) {
    var section = host.parentNode;
    if (!section || section.querySelector('.bfoot')) return;
    var ext = section.querySelector('.ext');
    var row = document.createElement('div');
    row.className = 'bfoot';
    if (ext) { ext.parentNode.insertBefore(row, ext); row.appendChild(ext); }
    else { section.appendChild(row); }
    row.insertAdjacentHTML('beforeend', IG_HTML);
  }

  function weather() {
    return getJSON('https://api.open-meteo.com/v1/forecast?latitude=' + LAT + '&longitude=' + LON +
      '&current=temperature_2m,precipitation,wind_speed_10m,wind_direction_10m' +
      '&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FPuerto_Rico')
      .then(function (j) { return j.current; });
  }
  function marineData(cfg) {
    return getJSON('https://marine-api.open-meteo.com/v1/marine?latitude=' + cfg.probe.latitude +
      '&longitude=' + cfg.probe.longitude +
      '&daily=wave_height_max,swell_wave_height_max,swell_wave_direction_dominant,swell_wave_period_max' +
      '&timezone=auto&forecast_days=1')
      .then(function (j) {
        var d = j.daily;
        return { h: d.swell_wave_height_max[0], dir: d.swell_wave_direction_dominant[0],
                 per: d.swell_wave_period_max[0] };   // swell, not total wave height
      });
  }

  Promise.all([getJSON('today.json'), getJSON('copy.json')]).then(function (r) {
    var today = r[0], copy = r[1];
    try { localStorage.setItem('sxm-today', JSON.stringify(today)); } catch (e) {}
    render(today, copy, null);

    weather().then(function (c) {
      if ($('wx-temp')) $('wx-temp').textContent =
        Math.round(c.temperature_2m) + '°F/' + Math.round((c.temperature_2m - 32) * 5 / 9) + '°C';
      if ($('wx-wind')) $('wx-wind').textContent =
        Math.round(c.wind_speed_10m) + ' mph ' + compass(c.wind_direction_10m);
      windKt = c.wind_speed_10m * 0.868;   // mph -> kt
      if ($('wx-rain')) $('wx-rain').textContent = Math.round(c.precipitation * 100) + '%';
    }).catch(function () {});

    marineData(today.swell_config)
      .then(function (m) { render(today, copy, m); })
      .catch(function () {});
  }).catch(function () {});
})();
