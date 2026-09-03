const state = {
  events: window.HER_MATCH_EVENTS || [],
  league: "All",
  query: "",
  limit: 10,
  selected: new Set(),
};

const $ = (id) => document.getElementById(id);
const clean = (text) => text.replace(/^⚽️?\s*/, "");

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

const shortLeague = (name) => {
  if (name.includes("National")) return "NWSL";
  if (name.includes("Northern")) return "NSL";
  if (name.includes("Super League")) return "WSL";
  return name;
};

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
    .map(
      (league) =>
        `<button class="filter ${state.league === league ? "active" : ""}" ` +
        `data-league="${escapeHtml(league)}">` +
        `${escapeHtml(league === "All" ? "All leagues" : shortLeague(league))}` +
        `</button>`,
    )
    .join("");

  document.querySelectorAll(".filter").forEach((button) => {
    button.onclick = () => {
      state.league = button.dataset.league;
      state.limit = 10;
      render();
    };
  });
}

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
      <span class="event-time">${date.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      })}</span>
    </div>
    <p class="event-location">${escapeHtml(
      event.location || "Location to be announced",
    )}</p>
    <span class="league-label">${escapeHtml(shortLeague(event.competition))}</span>
    <input class="select-event" type="checkbox"
      aria-label="Select ${escapeHtml(clean(event.title))}"
      data-id="${escapeHtml(event.id)}" ${selected}>
  </article>`;
}

function render() {
  renderFilters();
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
    };
  });
}

function escapeIcs(value = "") {
  return value
    .replace(/\r/g, "")
    .replace(/\\/g, "\\\\")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;")
    .replace(/\n/g, "\\n");
}

function icsDate(value) {
  return new Date(value)
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
}

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
    `PRODID:-//Her Match//Calendar//EN\r\n` +
    `CALSCALE:GREGORIAN\r\n` +
    `${body}\r\n` +
    `END:VCALENDAR\r\n`;
  const blob = new Blob([calendar], { type: "text/calendar" });
  const link = document.createElement("a");

  link.href = URL.createObjectURL(blob);
  link.download = "her-match-calendar.ics";
  link.click();
  URL.revokeObjectURL(link.href);
}

function renderLeagues() {
  const cards = leagues
    .map((league) => {
      const count = state.events.filter(
        (event) => event.competition === league,
      ).length;

      return `<article class="league-card">
        <b>${escapeHtml(shortLeague(league))}</b>
        <div>
          <h3>${escapeHtml(league)}</h3>
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

render();
renderLeagues();
