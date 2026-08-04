/* TODAY IN SXM — shared banner client.
   Reads today.json (built daily by tools/build_today.py) plus live weather and
   marine data. Handles only what needs the current clock. Renders nothing for
   any state whose copy has not been written. */
(function () {
  'use strict';
  var LAT = 18.03, LON = -63.05;
  var $ = function (id) { return document.getElementById(id); };
  if (!$('wx-advice')) return;

  var cache = function (k, v) {
    try { return v === undefined ? JSON.parse(localStorage.getItem(k) || 'null')
                                 : localStorage.setItem(k, JSON.stringify(v)); }
    catch (e) { return null; }
  };
  var getJSON = function (url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(r.status); return r.json();
    });
  };
  var pad = function (n) { return (n < 10 ? '0' : '') + n; };
  var mins = function (hhmm) { var p = hhmm.split(':'); return +p[0] * 60 + +p[1]; };
  var nowMins = function () { var d = new Date(); return d.getHours() * 60 + d.getMinutes(); };
  var compass = function (deg) {
    return ['N','NE','E','SE','S','SW','W','NW'][Math.round(((deg % 360) / 45)) % 8];
  };
  var list = function (a) {
    return a.length < 2 ? (a[0] || '') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1];
  };

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
        if (delta >= 0 && delta <= 45) { out.push('BRIDGE_UPCOMING'); break; }
        if (delta > -t.bridges.closure_minutes && delta <= 0) { out.push('BRIDGE_SINGLE'); break; }
      }
    }
    return out;
  }
  var PRIORITY = ['BRIDGE','TRAFFIC','ANOMALY','SWELL','SARGASSUM','CROWD','EVENT','CLOSURE','SPECIALS'];
  var EXCLUSIVE = [
    ['TRAFFIC_EMPTY','TRAFFIC_QUIET','TRAFFIC_NORMAL','TRAFFIC_BUSY','TRAFFIC_CONGESTED','TRAFFIC_GRIDLOCK','TRAFFIC_ZERO_SHIPS_STILL_BUSY','TRAFFIC_DATA_STALE'],
    ['SWELL_NORTH_WEST_ROUGH','SWELL_EAST_CHOPPY','SWELL_CALM','SWELL_DATA_STALE'],
    ['SARGASSUM_LIKELY','SARGASSUM_POSSIBLE','SARGASSUM_UNLIKELY']
  ];
  function resolve(slots, limit) {
    limit = limit || 3;
    var rank = function (s) {
      for (var i = 0; i < PRIORITY.length; i++) if (s.indexOf(PRIORITY[i]) === 0) return i;
      return PRIORITY.length;
    };
    var seen = {}, uniq = slots.filter(function (s) {
      if (seen[s]) return false; seen[s] = 1; return true;
    });
    uniq.sort(function (a, b) { return rank(a) - rank(b); });
    var out = [];
    uniq.forEach(function (s) {
      if (out.length >= limit) return;
      var clash = EXCLUSIVE.some(function (g) {
        return g.indexOf(s) > -1 && out.some(function (c) { return g.indexOf(c) > -1; });
      });
      if (!clash) out.push(s);
    });
    return out;
  }

  /* ---------------------------- render ---------------------------- */
  function render(t, copy, marine) {
    var d = new Date();
    if ($('wx-date')) {
      $('wx-date').textContent = d.toLocaleDateString('en-GB',
        { weekday: 'short', day: 'numeric', month: 'short' });
    }

    var tr = t.traffic;
    if ($('wx-ships')) {
      $('wx-ships').textContent = !tr.ships_known ? '—'
        : tr.ship_count === 0 ? 'No ships'
        : tr.ship_count + (tr.ship_count === 1 ? ' ship' : ' ships');
    }

    var slots = (t.slots || []).slice();
    slots = bridgeSlots(t).concat(slots);

    if (marine) {
      var st = swellState(marine.h, marine.dir, marine.per, t.swell_config);
      slots.push(st);
    }
    var n = nowMins(), cw = t.crowd_window;
    var heavy = ['BUSY','CONGESTED','GRIDLOCK'].indexOf(tr.severity) > -1;
    if (heavy && n >= mins(cw.start) && n <= mins(cw.end)) slots.push('CROWD_AVOID_LIST');

    var chosen = resolve(slots);

    var parts = [];
    if (tr.ships_known) {
      if (tr.ship_count === 0) {
        if (copy.ships.none) parts.push(copy.ships.none);
      } else if (copy.ships.some) {
        parts.push(copy.ships.some
          .replace('{ships}', list(tr.ships.map(function (s) { return s.ship; })))
          .replace('{pax}', tr.cruise_pax.toLocaleString()));
      }
    }
    chosen.forEach(function (s) {
      var line = copy.slots[s];
      if (line) parts.push(line);          // unwritten copy renders nothing
    });

    if ($('wx-advice')) {
      $('wx-advice').textContent = parts.join(' ');
      $('wx-advice').setAttribute('data-slots', chosen.join(','));
    }
  }

  function weather() {
    var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + LAT + '&longitude=' + LON +
      '&current=temperature_2m,precipitation,wind_speed_10m,wind_direction_10m' +
      '&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FPuerto_Rico';
    return getJSON(url).then(function (j) {
      var c = j.current;
      return { temp: c.temperature_2m, wind: c.wind_speed_10m, deg: c.wind_direction_10m,
               rain: c.precipitation };
    });
  }
  function marineData(cfg) {
    var url = 'https://marine-api.open-meteo.com/v1/marine?latitude=' + cfg.probe.latitude +
      '&longitude=' + cfg.probe.longitude +
      '&daily=wave_height_max,swell_wave_height_max,swell_wave_direction_dominant,swell_wave_period_max' +
      '&timezone=auto&forecast_days=1';
    return getJSON(url).then(function (j) {
      var d = j.daily;
      return { h: d.swell_wave_height_max[0], dir: d.swell_wave_direction_dominant[0],
               per: d.swell_wave_period_max[0] };
    });
  }

  Promise.all([
    getJSON('today.json'),
    getJSON('copy.json'),
  ]).then(function (r) {
    var today = r[0], copy = r[1];
    cache('sxm-today', today);
    render(today, copy, null);

    weather().then(function (w) {
      if ($('wx-temp')) $('wx-temp').textContent =
        Math.round(w.temp) + '°F/' + Math.round((w.temp - 32) * 5 / 9) + '°C';
      if ($('wx-wind')) $('wx-wind').textContent = Math.round(w.wind) + ' mph ' + compass(w.deg);
      if ($('wx-rain')) $('wx-rain').textContent = Math.round(w.rain * 100) + '%';
    }).catch(function () {});

    marineData(today.swell_config)
      .then(function (m) { render(today, copy, m); })
      .catch(function () {});
  }).catch(function () {
    var c = cache('sxm-today');
    if (c && $('wx-advice')) $('wx-advice').textContent = '';
  });
})();
