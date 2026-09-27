const API_BASE_URL = 'http://127.0.0.1:8000';
const REFRESH = { buses: 2_000, summary: 5_000, activity: 10_000, analytics: 15_000, routes: 30_000 };

const ui = {
  connection: document.getElementById('connection-label'),
  connectionWrap: document.querySelector('.system-status'),
  lastUpdated: document.getElementById('last-updated'),
  busesBody: document.getElementById('buses-body'),
  arrivalsBody: document.getElementById('arrivals-body'),
  delaysBody: document.getElementById('delays-body'),
  routePerformance: document.getElementById('route-performance'),
  congestion: document.getElementById('congestion-list'),
  alerts: document.getElementById('alerts-list'),
  routeFilter: document.getElementById('route-filter'),
  statusFilter: document.getElementById('status-filter'),
  search: document.getElementById('bus-search'),
};

let latestBuses = [];
let markers = new Map();
let map;
let mapHasFitted = false;
const inFlight = new Set();

if (window.L) {
  map = L.map('bus-map', { zoomControl: true }).setView([28.45, 77.055], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
} else {
  document.getElementById('bus-map').innerHTML =
    '<div class="empty-state">Map library could not load. Check your internet connection.</div>';
}

function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
}

function statusClass(status) {
  const normalized = String(status ?? '').toLowerCase();
  return ['normal', 'slow', 'critical'].includes(normalized) ? normalized : 'normal';
}

function formatNumber(value, digits = 1) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '—';
}

function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDuration(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  const seconds = Math.round(Number(value));
  const absolute = Math.abs(seconds);
  const amount = absolute < 60
    ? `${absolute}s`
    : `${Math.floor(absolute / 60)}m${absolute % 60 ? ` ${absolute % 60}s` : ''}`;
  if (seconds > 0) return `${amount} late`;
  if (seconds < 0) return `${amount} early`;
  return 'On time';
}

async function getJSON(path) {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function refresh(key, action) {
  if (inFlight.has(key)) return;
  inFlight.add(key);
  try {
    await action();
  } catch (error) {
    console.error(`TransitPulse ${key} refresh failed:`, error);
  } finally {
    inFlight.delete(key);
  }
}

function selectedBuses() {
  const route = ui.routeFilter.value;
  const status = ui.statusFilter.value.toLowerCase();
  const search = ui.search.value.trim().toLowerCase();
  return latestBuses.filter((bus) => {
    const matchesRoute = !route || bus.route === route;
    const matchesStatus = !status || String(bus.status ?? '').toLowerCase() === status;
    const matchesSearch = !search || `${bus.bus_id} ${bus.route}`.toLowerCase().includes(search);
    return matchesRoute && matchesStatus && matchesSearch;
  });
}

function updateRouteFilter(buses) {
  const current = ui.routeFilter.value;
  const routes = [...new Set(buses.map((bus) => bus.route).filter(Boolean))].sort();
  ui.routeFilter.innerHTML = '<option value="">All routes</option>'
    + routes.map((route) => `<option value="${escapeHTML(route)}">${escapeHTML(route)}</option>`).join('');
  ui.routeFilter.value = routes.includes(current) ? current : '';
}

function drawMarker(bus) {
  const status = statusClass(bus.status);
  const label = escapeHTML(String(bus.bus_id ?? '').replace(/^B/i, ''));
  return L.divIcon({
    className: 'bus-marker-wrap',
    html: `<div class="bus-marker ${status}"><span>${label}</span></div>`,
    iconSize: [27, 27],
    iconAnchor: [13, 25],
    popupAnchor: [0, -24],
  });
}

function renderMap(buses) {
  if (!map) return;
  const shown = new Set();
  const bounds = [];
  for (const bus of buses) {
    const lat = Number(bus.latitude);
    const lon = Number(bus.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    const id = String(bus.bus_id);
    shown.add(id);
    bounds.push([lat, lon]);
    const popup = `<strong>${escapeHTML(id)} · Route ${escapeHTML(bus.route)}</strong><br>`
      + `${escapeHTML(bus.status ?? 'Unknown')} · ${formatNumber(bus.speed)} km/h`;
    let marker = markers.get(id);
    if (marker) {
      marker.setLatLng([lat, lon]);
      if (marker.options.statusClass !== statusClass(bus.status)) {
        marker.setIcon(drawMarker(bus));
        marker.options.statusClass = statusClass(bus.status);
      }
      marker.setPopupContent(popup);
    } else {
      marker = L.marker([lat, lon], { icon: drawMarker(bus) }).bindPopup(popup).addTo(map);
      marker.options.statusClass = statusClass(bus.status);
      markers.set(id, marker);
    }
  }
  for (const [id, marker] of markers) {
    if (!shown.has(id)) {
      map.removeLayer(marker);
      markers.delete(id);
    }
  }
  if (!mapHasFitted && bounds.length) {
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 13 });
    mapHasFitted = true;
  }
  document.getElementById('map-count').textContent = `${buses.length} filtered locations`;
}

function renderBusTable() {
  const buses = selectedBuses();
  if (!buses.length) {
    ui.busesBody.innerHTML = `<tr><td colspan="7" class="empty-cell">${latestBuses.length ? 'No buses match these filters.' : 'No bus data available.'}</td></tr>`;
  } else {
    ui.busesBody.innerHTML = buses.map((bus) => {
      const status = statusClass(bus.status);
      return `<tr>
        <td><span class="bus-id">${escapeHTML(bus.bus_id)}</span></td>
        <td><span class="route-chip">${escapeHTML(bus.route)}</span></td>
        <td>${formatNumber(bus.speed)} <span class="unit">km/h</span></td>
        <td><span class="fleet-status ${status}">${escapeHTML(bus.status ?? 'Unknown')}</span></td>
        <td class="coordinate">${formatNumber(bus.latitude, 5)}</td>
        <td class="coordinate">${formatNumber(bus.longitude, 5)}</td>
        <td>${formatTime(bus.timestamp)}</td>
      </tr>`;
    }).join('');
  }
  document.getElementById('fleet-count').textContent = `${buses.length} of ${latestBuses.length} buses`;
  renderMap(buses);
}

async function loadBuses() {
  const buses = await getJSON('/buses');
  latestBuses = Array.isArray(buses) ? buses : [];
  updateRouteFilter(latestBuses);
  renderBusTable();
  ui.connection.textContent = 'API connected';
  ui.connectionWrap.classList.remove('offline');
  ui.lastUpdated.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

async function loadSummary() {
  const summary = await getJSON('/analytics/summary');
  document.getElementById('summary-total').textContent = summary.total_buses ?? 0;
  document.getElementById('summary-normal').textContent = summary.normal_buses ?? 0;
  document.getElementById('summary-slow').textContent = summary.slow_buses ?? 0;
  document.getElementById('summary-critical').textContent = summary.critical_buses ?? 0;
  document.getElementById('summary-congested').textContent = summary.congested_buses ?? 0;
  document.getElementById('event-total').textContent = `Events recorded: ${Number(summary.total_events ?? 0).toLocaleString()}`;
}

async function loadRoutePerformance() {
  const routes = await getJSON('/analytics/routes');
  if (!Array.isArray(routes) || !routes.length) {
    ui.routePerformance.innerHTML = '<div class="empty-state">No route data available yet.</div>';
    return;
  }
  const maxEvents = Math.max(...routes.map((route) => Number(route.total_events) || 0), 1);
  ui.routePerformance.innerHTML = routes.map((route) => {
    const events = Number(route.total_events) || 0;
    const width = Math.max(2, Math.round(events / maxEvents * 100));
    return `<div class="route-row">
      <div class="route-row-heading"><strong>${escapeHTML(route.route)}</strong><span>${formatNumber(route.average_speed, 2)} km/h avg</span></div>
      <div class="route-bar"><span style="width:${width}%"></span></div>
      <div class="route-row-foot"><span>${events.toLocaleString()} GPS events</span><span>Route average speed</span></div>
    </div>`;
  }).join('');
}

function congestionClass(level) {
  const value = String(level ?? '').toLowerCase();
  if (value === 'congested') return 'congested';
  if (value === 'moderate') return 'moderate';
  if (value === 'normal') return 'clear';
  return 'unknown';
}

async function loadCongestion() {
  const routes = await getJSON('/analytics/congestion');
  if (!Array.isArray(routes) || !routes.length) {
    ui.congestion.innerHTML = '<div class="empty-state">No congestion data available yet.</div>';
    return;
  }
  ui.congestion.innerHTML = routes.map((route) => {
    const cssClass = congestionClass(route.congestion_level);
    return `<div class="congestion-row">
      <div class="congestion-route"><strong>${escapeHTML(route.route)}</strong><span class="congestion-badge ${cssClass}">${escapeHTML(route.congestion_level)}</span></div>
      <div class="congestion-speed">${formatNumber(route.average_speed, 2)} <span>km/h average</span></div>
      <div class="congestion-events">${Number(route.event_count ?? 0).toLocaleString()} events</div>
    </div>`;
  }).join('');
}

async function loadDelays() {
  const rows = await getJSON('/analytics/delays');
  if (!Array.isArray(rows) || !rows.length) {
    ui.delaysBody.innerHTML = '<tr><td colspan="4" class="empty-cell">No arrival delay data available yet.</td></tr>';
    return;
  }
  ui.delaysBody.innerHTML = rows.map((row) => `<tr>
    <td><span class="route-chip">${escapeHTML(row.route)}</span><span class="cell-secondary">${Number(row.arrival_count ?? 0)} arrivals</span></td>
    <td>${formatDuration(row.average_delay_seconds)}</td>
    <td>${formatDuration(row.maximum_delay_seconds)}</td>
    <td><span class="count-early">${row.early_count ?? 0}</span> / ${row.on_time_count ?? 0} / <span class="count-late">${row.late_count ?? 0}</span></td>
  </tr>`).join('');
}

async function loadAlerts() {
  const rows = await getJSON('/alerts');
  if (!Array.isArray(rows) || !rows.length) {
    ui.alerts.innerHTML = '<div class="empty-state">No active operational alerts.</div>';
    return;
  }
  ui.alerts.innerHTML = rows.slice(0, 12).map((alert) => {
    const severity = String(alert.severity ?? 'info').toLowerCase();
    const location = [alert.bus_id, alert.route].filter(Boolean).join(' · ');
    return `<article class="alert-row">
      <span class="alert-severity ${severity}"><i></i>${escapeHTML(severity)}</span>
      <div class="alert-copy"><strong>${escapeHTML(alert.message)}</strong><span>${escapeHTML(alert.alert_type.replaceAll('_', ' '))}${location ? ` · ${escapeHTML(location)}` : ''}</span></div>
      <time>${formatTime(alert.timestamp)}</time>
    </article>`;
  }).join('');
}

function delayBadge(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '<span class="delay-badge delay-ontime">Unknown</span>';
  const seconds = Math.round(Number(value));
  if (seconds === 0) return '<span class="delay-badge delay-ontime">On time</span>';
  const duration = formatDuration(Math.abs(seconds));
  const amount = duration.replace(' late', '').replace(' early', '');
  return seconds > 0
    ? `<span class="delay-badge delay-late">${amount} late</span>`
    : `<span class="delay-badge delay-early">${amount} early</span>`;
}

async function loadArrivals() {
  const rows = await getJSON('/arrivals');
  if (!Array.isArray(rows) || !rows.length) {
    ui.arrivalsBody.innerHTML = '<tr><td colspan="4" class="empty-cell">No stop arrivals recorded yet.</td></tr>';
    document.getElementById('arrivals-footer').textContent = 'Waiting for arrival events';
    return;
  }
  ui.arrivalsBody.innerHTML = rows.slice(0, 25).map((arrival) => `<tr>
    <td><span class="cell-primary">${escapeHTML(arrival.bus_id)}</span><span class="cell-secondary">Route ${escapeHTML(arrival.route)}</span></td>
    <td>${escapeHTML(arrival.stop)}</td>
    <td><span class="cell-primary">${formatTime(arrival.actual_arrival)}</span><span class="cell-secondary">Expected ${formatTime(arrival.expected_arrival)}</span></td>
    <td>${delayBadge(arrival.delay_seconds)}</td>
  </tr>`).join('');
  document.getElementById('arrivals-footer').textContent = `${rows.length} recent arrivals · newest first`;
}

async function tick(key, action, everyMs) {
  await refresh(key, async () => {
    try {
      await action();
    } catch (error) {
      if (key === 'buses') {
        ui.connection.textContent = 'API unavailable';
        ui.connectionWrap.classList.add('offline');
      }
      throw error;
    }
  });
  window.setTimeout(() => tick(key, action, everyMs), everyMs);
}

for (const control of [ui.routeFilter, ui.statusFilter]) control.addEventListener('change', renderBusTable);
ui.search.addEventListener('input', renderBusTable);

tick('buses', loadBuses, REFRESH.buses);
tick('summary', loadSummary, REFRESH.summary);
tick('routes', loadRoutePerformance, REFRESH.routes);
tick('congestion', loadCongestion, REFRESH.analytics);
tick('delays', loadDelays, REFRESH.analytics);
tick('alerts', loadAlerts, REFRESH.activity);
tick('arrivals', loadArrivals, REFRESH.activity);
