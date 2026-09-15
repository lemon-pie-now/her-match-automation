// Build the application's working state from the generated event feed.
// Filtering here prevents stale, already-started games from appearing when
// events.js was generated earlier than the visitor's current page load.
const state = {
  events: (window.RALLY49_EVENTS || []).filter(
    (event) => new Date(event.start) >= new Date(),
  ).sort((a, b) => new Date(a.start) - new Date(b.start)),
  league: "All",
  query: "",
  limit: 10,
  selected: new Set(),
};

const $ = (id) => document.getElementById(id);

// Some calendar feeds include a soccer-ball prefix that the UI does not need.
const clean = (text) => text.replace(/^⚽️?\s*/, "");

// Escape all feed-provided text before inserting it into HTML templates.
const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[character],
  );

const leagues = [...new Set(state.events.map((event) => event.competition))];

// Explicit metadata avoids confusing similarly named competitions.
const leagueDirectory = {
  "National Women’s Soccer League": { short: "NWSL", name: "National Women’s Soccer League", sport: "Soccer", country: "United States" },
  "Northern Super League": { short: "NSL", name: "Northern Super League", sport: "Soccer", country: "Canada" },
  "Women's Super League": { short: "WSL", name: "Women’s Super League", sport: "Soccer", country: "England" },
  "Women's Pro Baseball League": { short: "WPBL", name: "Women’s Pro Baseball League", sport: "Baseball", country: "United States" },
  "WNBA": { short: "WNBA", name: "Women’s National Basketball Association", sport: "Basketball", country: "United States & Canada" },
};
const leagueInfo = (name) => leagueDirectory[name] || {
  short: name, name,
  sport: state.events.find((event) => event.competition === name)?.sport || "Sport to be confirmed",
  country: "Country to be confirmed",
};
const shortLeague = (name) => leagueInfo(name).short;
const displayLeague = (name) => leagueInfo(name).name;
const leagueDetails = (name) => `${leagueInfo(name).sport} · ${leagueInfo(name).country}`;

// Apply the selected league and free-text search to the current event set.
function visible() {
  return state.events.filter(
    (event) =>
      (state.league === "All" || event.competition === state.league) &&
      `${event.title} ${event.competition}`
        .toLowerCase()
        .includes(state.query.toLowerCase()),
  );
}

function renderFilters() {
  $("leagueFilters").innerHTML = ["All", ...leagues]
    .map((league, index) => {
      const description = league === "All" ? "Browse every available league" : `${displayLeague(league)} · ${leagueDetails(league)}`;
      return `<span class="league-filter-wrap">
        <button class="filter" data-league="${escapeHtml(league)}" aria-describedby="league-tip-${index}">
          ${escapeHtml(league === "All" ? "All leagues" : shortLeague(league))}
        </button>
        <span class="league-tooltip" role="tooltip" id="league-tip-${index}">${escapeHtml(description)}</span>
      </span>`;
    })
    .join("");

  document.querySelectorAll(".filter").forEach((button) => {
    button.onclick = () => {
      state.league = button.dataset.league;
      state.limit = 10;
      render();
    };
  });
}

// Create one event row. Dates are formatted in the visitor's local timezone.
function eventMarkup(event) {
  const date = new Date(event.start);
  const selected = state.selected.has(event.id) ? "checked" : "";

  return `<article class="event">
    <div class="date-block">
      <strong>${date.toLocaleDateString(undefined, { day: "2-digit" })}</strong>
      <span>${date.toLocaleDateString(undefined, {
        month: "short",
        weekday: "short",
      })}</span>
    </div>
    <div>
      <h3>${escapeHtml(clean(event.title))}</h3>
      <span class="event-league">${escapeHtml(shortLeague(event.competition))} · ${escapeHtml(leagueDetails(event.competition))}</span>
      <span class="event-time">${date.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      })}</span>
    </div>
    <p class="event-location">${escapeHtml(
      event.location || "Location to be announced",
    )}</p>
    <input class="select-event" type="checkbox"
      aria-label="Select ${escapeHtml(clean(event.title))}"
      data-id="${escapeHtml(event.id)}" ${selected}>
  </article>`;
}

function renderDownloadButton() {
  const count = state.selected.size || visible().length;
  $("downloadCalendar").textContent = state.selected.size
    ? `Download ${count} selected game${count === 1 ? "" : "s"} ↓`
    : `Download all ${count} matching games ↓`;
  $("downloadCalendar").disabled = count === 0;
}

function renderHero() {
  $("upcomingCount").textContent = state.events.length.toLocaleString();
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  $("timezoneNote").textContent = `All game times shown in your local timezone: ${timezone}.`;
  const event = state.events[0];
  if (!event) {
    $("featuredGame").innerHTML = '<p>THE NEXT CHAPTER</p><h2>More games to look forward to.</h2><p>No upcoming games in the current schedule. Check back soon.</p>';
    return;
  }
  const date = new Date(event.start);
  $("featuredGame").innerHTML = `<p>UP NEXT · ${escapeHtml(shortLeague(event.competition))}</p>
    <h2>${escapeHtml(clean(event.title))}</h2>
    <p>${escapeHtml(date.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric", year: "numeric" }))}</p>
    <div><span>${escapeHtml(date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" }))}</span><a href="#calendar">Browse games ↘</a></div>`;
}

// Refresh results, counts, pagination, and selection handlers together so the
// interface stays consistent after any filter or search change.
function render() {
  document.querySelectorAll(".filter").forEach((button) => {
    const active = button.dataset.league === state.league;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("leagueSummary").textContent = state.league === "All"
    ? "All leagues · Sport and country shown with each game"
    : `${displayLeague(state.league)} · ${leagueDetails(state.league)}`;
  renderDownloadButton();
  const events = visible();
  const shown = events.slice(0, state.limit);

  $("resultCount").textContent =
    `${events.length} upcoming match${events.length === 1 ? "" : "es"}`;
  $("eventList").innerHTML = shown.length
    ? shown.map(eventMarkup).join("")
    : '<div class="empty">No matches found. Try a different search or league.</div>';
  $("loadMore").style.display = events.length > state.limit ? "block" : "none";

  document.querySelectorAll(".select-event").forEach((checkbox) => {
    checkbox.onchange = () => {
      if (checkbox.checked) state.selected.add(checkbox.dataset.id);
      else state.selected.delete(checkbox.dataset.id);
      renderDownloadButton();
    };
  });
}

// ICS text fields require escaping for slashes, separators, and newlines.
function escapeIcs(value = "") {
  return value
    .replace(/\r/g, "")
    .replace(/\\/g, "\\\\")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;")
    .replace(/\n/g, "\\n");
}

// Calendar files expect compact UTC timestamps such as 20260910T230000Z.
function icsDate(value) {
  return new Date(value)
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
}

// Export selected games, or all currently visible games when none are selected.
function download() {
  const chosen = state.selected.size
    ? state.events.filter((event) => state.selected.has(event.id))
    : visible();

  if (!chosen.length) return;

  const body = chosen
    .map(
      (event) =>
        `BEGIN:VEVENT\r\n` +
        `UID:${event.id}@hermatch.ca\r\n` +
        `DTSTAMP:${icsDate(new Date())}\r\n` +
        `DTSTART:${icsDate(event.start)}\r\n` +
        `DTEND:${icsDate(event.end)}\r\n` +
        `SUMMARY:${escapeIcs(clean(event.title))}\r\n` +
        `LOCATION:${escapeIcs(event.location)}\r\n` +
        `DESCRIPTION:${escapeIcs(event.competition)}\r\n` +
        `END:VEVENT`,
    )
    .join("\r\n");
  const calendar =
    `BEGIN:VCALENDAR\r\n` +
    `VERSION:2.0\r\n` +
    `PRODID:-//Rally49//Calendar//EN\r\n` +
    `CALSCALE:GREGORIAN\r\n` +
    `${body}\r\n` +
    `END:VCALENDAR\r\n`;
  const blob = new Blob([calendar], { type: "text/calendar" });
  const link = document.createElement("a");

  link.href = URL.createObjectURL(blob);
  link.download = "rally49-calendar.ics";
  link.click();
  URL.revokeObjectURL(link.href);
}

// Build the league overview using counts from the same filtered event state.
function renderLeagues() {
  const cards = leagues
    .map((league) => {
      const count = state.events.filter(
        (event) => event.competition === league,
      ).length;

      return `<article class="league-card">
        <b>${escapeHtml(shortLeague(league))}</b>
        <div>
          <h3>${escapeHtml(displayLeague(league))}</h3>
          <p class="league-details">${escapeHtml(leagueDetails(league))}</p>
          <p>${count} upcoming matches</p>
        </div>
      </article>`;
    })
    .join("");

  $("leagueGrid").innerHTML =
    cards +
    `<article class="league-card">
      <b>+</b>
      <div>
        <h3>More coming soon</h3>
        <p>Basketball, hockey, tennis, and more.</p>
      </div>
    </article>`;
}

// Wire page controls after all helpers have been defined.
$("search").oninput = (event) => {
  state.query = event.target.value;
  state.limit = 10;
  render();
};

$("clearFilters").onclick = () => {
  state.league = "All";
  state.query = "";
  $("search").value = "";
  render();
};

$("loadMore").onclick = () => {
  state.limit += 10;
  render();
};

$("downloadCalendar").onclick = download;

// Perform the initial page render.
renderHero();
renderFilters();
render();
renderLeagues();
