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
  function swellState(h, dir, per, cfg) {
    if (h == null || dir == null) return 'SWELL_DATA_STALE';
    if (per != null && per >= cfg.groundswell_min_period &&
        inArc(dir, cfg.nw_arc) && h >= cfg.min_height) return 'SWELL_NORTH_WEST_ROUGH';
    if (inArc(dir, cfg.e_arc) && h >= cfg.min_height) return 'SWELL_EAST_CHOPPY';
    return 'SWELL_CALM';
  }
  function bridgeSlots(t) {
    var out = [], n = nowMins();
    (t.bridges.compound_windows || []).forEach(function (w) {
      if (n >= mins(w.start) && n <= mins(w.end)) out.push(w.key);
    });
    if (!out.length) {
      var all = [];
      Object.keys(t.bridges.schedule).forEach(function (k) {
        t.bridges.schedule[k].times.forEach(function (x) { all.push(mins(x)); });
      });
      all.sort(function (a, b) { return a - b; });
      for (var i = 0; i < all.length; i++) {
        var delta = all[i] - n;
        if (delta > -t.bridges.closure_minutes && delta <= 0) { out.push('BRIDGE_SINGLE'); break; }
        if (delta > 0 && delta <= 45) { out.push('BRIDGE_UPCOMING'); break; }
      }
    }
    return out;
  }

  /* ---- grouping: cap per category, never drop a whole subject ---- */
  var GROUPS = [
    { key: 'ROADS',   label: 'ROADS',     max: 2, match: /^(TRAFFIC|ANOMALY)_/ },
    { key: 'BRIDGES', label: 'BRIDGES',   max: 1, match: /^BRIDGE_/ },
    { key: 'WATER',   label: 'WATER',     max: 1, match: /^SWELL_/ },
    { key: 'BEACHES', label: 'BEACHES',   max: 2, match: /^(SARGASSUM|CROWD)_/ },
    { key: 'WHATSON', label: "WHAT'S ON", max: 2, match: /^(EVENT|CLOSURE|SPECIALS)_/ }
  ];
  var EXCLUSIVE = [
    ['TRAFFIC_EMPTY','TRAFFIC_QUIET','TRAFFIC_NORMAL','TRAFFIC_BUSY','TRAFFIC_CONGESTED',
     'TRAFFIC_GRIDLOCK','TRAFFIC_ZERO_SHIPS_STILL_BUSY','TRAFFIC_DATA_STALE'],
    ['SWELL_NORTH_WEST_ROUGH','SWELL_EAST_CHOPPY','SWELL_CALM','SWELL_DATA_STALE'],
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
    '.brow{display:grid;grid-template-columns:58px 1fr;gap:9px;padding:5px 0;border-top:1px solid #EFDCB4}' +
    '.brow:first-child{border-top:0;padding-top:0}' +
    '.bk{font-family:Montserrat,sans-serif;font-weight:700;font-size:8px;letter-spacing:.11em;color:#A6813C;padding-top:2px}' +
    '.bv{font-size:11.5px;color:#7A5410;line-height:1.45;margin:0}' +
    '@media(min-width:820px){.brow{grid-template-columns:74px 1fr}.bv{font-size:13px}}';
  var st = document.createElement('style'); st.textContent = CSS;
  document.head.appendChild(st);

  /* ---------------------------- render ---------------------------- */
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
    if (marine) slots.push(swellState(marine.h, marine.dir, marine.per, t.swell_config));

    var n = nowMins(), cw = t.crowd_window;
    if (['BUSY','CONGESTED','GRIDLOCK'].indexOf(tr.severity) > -1 &&
        n >= mins(cw.start) && n <= mins(cw.end)) slots.push('CROWD_AVOID_LIST');

    var monthName = MONTHS[new Date(t.date + 'T12:00:00').getMonth()];
    var line = function (k) {
      var l = copy.slots[k];
      return l ? l.replace('{month}', monthName) : '';
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

    var rows = [], used = [];
    group(slots).forEach(function (g) {
      var parts = g.slots.map(line).filter(Boolean);
      if (g.key === 'ROADS' && shipsLine) parts.unshift(shipsLine);
      if (!parts.length) return;                       // silent category disappears
      used = used.concat(g.slots);
      rows.push('<div class="brow"><div class="bk">' + g.label +
                '</div><p class="bv">' + parts.join(' ') + '</p></div>');
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
                 per: d.swell_wave_period_max[0] };
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
      if ($('wx-rain')) $('wx-rain').textContent = Math.round(c.precipitation * 100) + '%';
    }).catch(function () {});

    marineData(today.swell_config)
      .then(function (m) { render(today, copy, m); })
      .catch(function () {});
  }).catch(function () {});
})();
