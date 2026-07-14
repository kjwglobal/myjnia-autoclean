const state = {
  services: [],
  addons: [],
  bookings: [],
  myBookings: [],
  availability: null,
  ownerDayPlan: [],
  ownerSchedule: null,
  ownerMessages: [],
  clientProfile: null,
  clientVehicles: [],
  clientNotifications: { items: [], unread_count: 0 },
  dashboard: {},
  user: null,
};

const PAGE_BY_PATH = {
  "/": "home",
  "/index.html": "home",
  "/konto.html": "account",
  "/rezerwacja.html": "booking",
  "/panel-klienta.html": "client-panel",
  "/panel-wlasciciela.html": "owner-panel",
};

const DEFAULT_PANEL_TABS = {
  client: "visits",
  owner: "overview",
};

function currentPage() {
  return PAGE_BY_PATH[window.location.pathname] || "home";
}

function routeForRole(role) {
  return role === "owner" ? "/panel-wlasciciela.html" : "/panel-klienta.html";
}

function safeNextPath() {
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//")) return null;
  return next;
}

function redirectTo(path) {
  if (window.location.pathname === path) return false;
  window.location.assign(path);
  return true;
}

function setPageChrome() {
  const page = currentPage();
  const hash = window.location.hash;
  document.body.dataset.page = page;
  document.querySelectorAll("[data-nav-page]").forEach((link) => {
    const href = link.getAttribute("href") || "";
    const isActive = page === "home"
      ? Boolean(hash && href.endsWith(hash))
      : link.dataset.navPage === page;
    link.classList.toggle("active", isActive);
  });
}

function enforcePageAccess() {
  const page = currentPage();

  if (page === "client-panel") {
    if (!state.user) return redirectTo("/konto.html?next=/panel-klienta.html");
    if (state.user.role !== "client") return redirectTo(routeForRole(state.user.role));
  }

  if (page === "owner-panel") {
    if (!state.user) return redirectTo("/konto.html?next=/panel-wlasciciela.html");
    if (state.user.role !== "owner") return redirectTo(routeForRole(state.user.role));
  }

  if (page === "booking" && state.user?.role === "owner") {
    return redirectTo("/panel-wlasciciela.html");
  }

  return false;
}

function redirectAfterAuth() {
  const next = safeNextPath();
  if (next) {
    redirectTo(next);
    return;
  }
  redirectTo(routeForRole(state.user?.role));
}

const money = new Intl.NumberFormat("pl-PL", {
  style: "currency",
  currency: "PLN",
  maximumFractionDigits: 0,
});

const dateTime = new Intl.DateTimeFormat("pl-PL", {
  weekday: "short",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const dayDate = new Intl.DateTimeFormat("pl-PL", {
  weekday: "long",
  day: "2-digit",
  month: "long",
});

const timeOnly = new Intl.DateTimeFormat("pl-PL", {
  hour: "2-digit",
  minute: "2-digit",
});

const STATUS_LABELS = {
  new: "nowa",
  confirmed: "potwierdzona",
  in_progress: "w trakcie",
  completed: "gotowa",
  cancelled: "anulowana",
  no_show: "brak",
};

const STATUS_OPTIONS = [
  "new",
  "confirmed",
  "in_progress",
  "completed",
  "cancelled",
  "no_show",
];

const WEEKDAY_LABELS = [
  "Poniedzialek",
  "Wtorek",
  "Sroda",
  "Czwartek",
  "Piatek",
  "Sobota",
  "Niedziela",
];

const byId = (id) => document.getElementById(id);

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value;
}

function setHtml(id, value) {
  const element = byId(id);
  if (element) element.innerHTML = value;
}

function setHidden(element, hidden) {
  if (element) element.classList.toggle("hidden", hidden);
}

function panelDatasetKey(scope) {
  return `${scope}Tab`;
}

function activePanelTab(scope) {
  return document.body.dataset[panelDatasetKey(scope)] || DEFAULT_PANEL_TABS[scope];
}

function setActivePanelTab(scope, target) {
  document.body.dataset[panelDatasetKey(scope)] = target;
  syncPanelTabs(scope);
}

function syncPanelTabs(scope) {
  const buttons = [...document.querySelectorAll(`[data-panel-scope="${scope}"][data-panel-tab]`)];
  const sections = [...document.querySelectorAll(`[data-panel-scope="${scope}"][data-panel-section]`)];
  if (!buttons.length && !sections.length) return;

  let target = activePanelTab(scope);
  const hasTarget = buttons.some((button) => button.dataset.panelTab === target);
  if (!hasTarget) {
    target = buttons[0]?.dataset.panelTab || DEFAULT_PANEL_TABS[scope];
  }
  document.body.dataset[panelDatasetKey(scope)] = target;

  buttons.forEach((button) => {
    const isActive = button.dataset.panelTab === target;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  sections.forEach((section) => {
    const names = String(section.dataset.panelSection || "").split(/\s+/);
    setHidden(section, !names.includes(target));
  });
}

function syncAllPanelTabs() {
  syncPanelTabs("client");
  syncPanelTabs("owner");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatMoney(value) {
  return money.format(Number(value || 0)).replace("PLN", "zl");
}

function formatMinutes(minutes) {
  const value = Number(minutes || 0);
  if (value < 60) return `${value} min`;
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

function formatDate(value) {
  if (!value) return "--";
  return dateTime.format(new Date(value.replace(" ", "T")));
}

function formatTime(value) {
  if (!value) return "--";
  return timeOnly.format(new Date(value.replace(" ", "T")));
}

function formatDay(value) {
  if (!value) return "--";
  return dayDate.format(dateFromInputValue(value));
}

function roleLabel(role) {
  return role === "owner" ? "Wlasciciel" : "Klient";
}

function toDateInputValue(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function dateFromInputValue(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  return new Date(year, month - 1, day);
}

function addDays(value, days) {
  const date = dateFromInputValue(value);
  date.setDate(date.getDate() + days);
  return toDateInputValue(date);
}

function setDefaultBookingDate() {
  const input = byId("booking-date");
  const startsAt = byId("starts-at");
  if (!input) return;
  const today = new Date();
  const date = new Date();
  date.setDate(date.getDate() + 1);
  input.min = toDateInputValue(today);
  input.value = toDateInputValue(date);
  if (startsAt) startsAt.value = "";
}

function setDefaultOwnerPlanDate() {
  const input = byId("owner-plan-date");
  if (!input) return;
  input.value = toDateInputValue(new Date());
}

function renderSettings(settings) {
  document.querySelectorAll("[data-setting]").forEach((node) => {
    const key = node.dataset.setting;
    if (settings[key]) node.textContent = settings[key];
  });
  if (settings.business_name) {
    document.title = settings.business_name;
  }
}

function renderServices() {
  const servicesList = byId("services-list");
  const serviceChoices = byId("service-choices");

  if (servicesList) {
    servicesList.innerHTML = state.services
      .map(
        (service) => `
          <article class="service-card">
            <div>
              <h3>${escapeHtml(service.name)}</h3>
              <p>${escapeHtml(service.description)}</p>
            </div>
            <div class="service-meta">
              <span class="price">${formatMoney(service.base_price_pln)}</span>
              <span class="duration">${formatMinutes(service.duration_minutes)}</span>
            </div>
          </article>
        `,
      )
      .join("");
  }

  if (serviceChoices) {
    serviceChoices.innerHTML = state.services
      .map(
        (service, index) => `
          <label class="choice-card">
            <input type="radio" name="service_ids" value="${service.id}" ${index === 0 ? "checked" : ""} />
            <strong>${escapeHtml(service.name)}</strong>
            <span>${formatMoney(service.base_price_pln)} · ${formatMinutes(service.duration_minutes)}</span>
          </label>
        `,
      )
      .join("");
  }
}

function renderAddons() {
  setHtml(
    "addon-choices",
    state.addons
      .map(
        (addon) => `
          <label class="addon-item">
            <input type="checkbox" name="addon_ids" value="${addon.id}" />
            <strong>${escapeHtml(addon.name)}</strong>
            <span>${formatMoney(addon.price_pln)} · ${formatMinutes(addon.duration_minutes)}</span>
          </label>
        `,
      )
      .join(""),
  );
}

function renderDashboard() {
  const byStatus = state.dashboard.by_status || {};
  setText("today-count", state.dashboard.today_count || 0);
  setText("stat-new", byStatus.new || 0);
  setText("stat-confirmed", byStatus.confirmed || 0);
  setText("stat-revenue", formatMoney(state.dashboard.revenue_pln || 0));
  setText("owner-customers", state.dashboard.customer_count || 0);
  setText("owner-week-count", state.dashboard.week_count || 0);
  setText("owner-messages-count", state.dashboard.unread_messages || 0);
  setText("owner-pending-payments", formatMoney(state.dashboard.pending_payments_pln || 0));

  const ownerUpcoming = state.bookings.find(
    (booking) => new Date(booking.starts_at.replace(" ", "T")) >= new Date(),
  );
  const nextSlot = ownerUpcoming?.starts_at || state.dashboard.next_slot;
  setText("next-slot", nextSlot ? formatDate(nextSlot) : "wolne");
}

function bookingCards(bookings, options = {}) {
  if (!bookings.length) {
    return `<p class="empty">${escapeHtml(options.emptyText || "Brak wizyt w planie.")}</p>`;
  }

  return bookings
    .map(
      (booking) => `
        <article class="booking-card">
          <header>
            <div>
              <h3>${formatDate(booking.starts_at)}${options.showCustomer === false ? "" : " · " + escapeHtml(booking.customer_name)}</h3>
              <p>${escapeHtml(booking.services || "Usluga")} · ${formatMoney(booking.total_price_pln)}</p>
            </div>
            <span class="badge ${escapeHtml(booking.status)}">${statusLabel(booking.status)}</span>
          </header>
          <p>${escapeHtml(booking.vehicle || "Auto")} ${booking.registration_number ? "· " + escapeHtml(booking.registration_number) : ""}</p>
          ${booking.addons ? `<p>Dodatki: ${escapeHtml(booking.addons)}</p>` : ""}
          ${booking.customer_notes ? `<p>Uwagi: ${escapeHtml(booking.customer_notes)}</p>` : ""}
          ${
            options.clientDetails
              ? `
                <dl class="booking-details">
                  <div><dt>Od</dt><dd>${formatDate(booking.starts_at)}</dd></div>
                  <div><dt>Do</dt><dd>${formatDate(booking.ends_at)}</dd></div>
                  <div><dt>Status</dt><dd>${statusLabel(booking.status)}</dd></div>
                  <div><dt>Kwota</dt><dd>${formatMoney(booking.total_price_pln)}</dd></div>
                </dl>
              `
              : ""
          }
          ${
            options.editableStatus
              ? `
                <form class="booking-status-form" data-booking-id="${booking.id}">
                  <label>
                    Status
                    <select name="status">
                      ${statusOptions(booking.status)}
                    </select>
                  </label>
                  <button class="button dark" type="submit">Zapisz status</button>
                </form>
              `
              : ""
          }
          ${
            options.clientActions
              ? `
                <form class="client-cancel-form" data-booking-id="${booking.id}">
                  <button class="button dark" type="submit" ${Number(booking.can_cancel) ? "" : "disabled"}>
                    Odwolaj wizyte
                  </button>
                </form>
              `
              : ""
          }
        </article>
      `,
    )
    .join("");
}

function statusOptions(currentStatus) {
  return STATUS_OPTIONS.map(
    (status) => `
      <option value="${status}" ${status === currentStatus ? "selected" : ""}>
        ${STATUS_LABELS[status]}
      </option>
    `,
  ).join("");
}

function renderOwnerWorkspace() {
  const upcoming = state.bookings
    .filter((booking) => new Date(booking.starts_at.replace(" ", "T")) >= new Date())
    .slice(0, 5);

  setHtml(
    "owner-next-bookings",
    upcoming.length
      ? upcoming
          .map(
            (booking) => `
              <article class="owner-list-item">
                <strong>${formatDate(booking.starts_at)} · ${escapeHtml(booking.customer_name)}</strong>
                <span>${escapeHtml(booking.services || "Usluga")} · ${escapeHtml(booking.phone || "")}</span>
              </article>
            `,
          )
          .join("")
      : `<p class="empty">Brak nadchodzacych wizyt.</p>`,
  );

  setHtml(
    "owner-messages-list",
    state.ownerMessages.length
      ? state.ownerMessages
          .map(
            (message) => `
              <article class="owner-list-item">
                <strong>${escapeHtml(message.subject)} · ${escapeHtml(message.name)}</strong>
                <span>${escapeHtml(message.email)}${message.phone ? " · " + escapeHtml(message.phone) : ""}</span>
                <p>${escapeHtml(message.message)}</p>
              </article>
            `,
          )
          .join("")
      : `<p class="empty">Brak wiadomosci.</p>`,
  );

  renderOwnerDayPlan();
  renderOwnerSchedule();
  renderOwnerPricing();
}

function renderOwnerDayPlan() {
  const plan = byId("owner-day-plan");
  if (!plan) return;

  plan.innerHTML = state.ownerDayPlan.length
    ? state.ownerDayPlan
        .map(
          (booking) => `
            <article class="day-plan-item">
              <div class="day-plan-time">
                <strong>${formatTime(booking.starts_at)}</strong>
                <span>${formatTime(booking.ends_at)}</span>
              </div>
              <div>
                <strong>${escapeHtml(booking.customer_name)}</strong>
                <span>${escapeHtml(booking.services || "Usluga")} · ${escapeHtml(booking.vehicle || "Auto")}</span>
                <small>${escapeHtml(booking.registration_number || "")} ${booking.phone ? "· " + escapeHtml(booking.phone) : ""}</small>
              </div>
              <span class="badge ${escapeHtml(booking.status)}">${statusLabel(booking.status)}</span>
            </article>
          `,
        )
        .join("")
    : `<p class="empty">Brak wizyt w tym dniu.</p>`;
}

function renderOwnerSchedule() {
  const schedule = state.ownerSchedule || { hours: [], closures: [], station_count: 1 };
  const list = byId("owner-hours-list");
  const stationInput = byId("owner-schedule-form")?.elements.station_count;
  const closuresList = byId("owner-closures-list");
  if (!list || !stationInput || !closuresList) return;

  stationInput.value = Number(schedule.station_count || 1);
  list.innerHTML = WEEKDAY_LABELS.map((label, weekday) => {
    const row = (schedule.hours || []).find((item) => Number(item.weekday) === weekday) || {
      weekday,
      is_open: weekday < 5,
      opens_at: weekday === 5 ? "09:00" : "08:00",
      closes_at: weekday === 5 ? "15:00" : "18:00",
    };
    return `
      <div class="schedule-day-row ${row.is_open ? "" : "closed"}" data-weekday="${weekday}">
        <label class="schedule-open-toggle">
          <input name="is_open" type="checkbox" ${row.is_open ? "checked" : ""} />
          <span>${label}</span>
        </label>
        <label>
          Od
          <input name="opens_at" type="time" value="${escapeHtml(row.opens_at || "09:00")}" />
        </label>
        <label>
          Do
          <input name="closes_at" type="time" value="${escapeHtml(row.closes_at || "17:00")}" />
        </label>
      </div>
    `;
  }).join("");

  closuresList.innerHTML = schedule.closures?.length
    ? schedule.closures
        .map(
          (closure) => `
            <form class="closure-item closure-delete-form" data-id="${closure.id}">
              <div>
                <strong>${escapeHtml(closure.date)}</strong>
                <span>${escapeHtml(closure.reason || "Dzien wolny")}</span>
              </div>
              <button class="button dark" type="submit">Usun</button>
            </form>
          `,
        )
        .join("")
    : `<p class="empty">Brak dodatkowych dni wolnych.</p>`;
  syncScheduleRows();
}

function syncScheduleRows() {
  document.querySelectorAll(".schedule-day-row").forEach((row) => {
    const isOpen = row.querySelector('[name="is_open"]')?.checked;
    row.classList.toggle("closed", !isOpen);
    row.querySelectorAll('input[type="time"]').forEach((input) => {
      input.disabled = !isOpen;
    });
  });
}

function renderOwnerPricing() {
  const pricingList = byId("owner-pricing-list");
  if (!pricingList) return;

  const serviceRows = state.services.map((service) => ({
    type: "service",
    eyebrow: "Usluga",
    id: service.id,
    name: service.name,
    description: service.description,
    duration_minutes: service.duration_minutes,
    price_pln: service.base_price_pln,
  }));
  const addonRows = state.addons.map((addon) => ({
    type: "addon",
    eyebrow: "Dodatek",
    id: addon.id,
    name: addon.name,
    description: addon.description,
    duration_minutes: addon.duration_minutes,
    price_pln: addon.price_pln,
  }));

  pricingList.innerHTML = [...serviceRows, ...addonRows]
    .map(
      (item) => `
        <form class="pricing-form" data-type="${item.type}" data-id="${item.id}">
          <div class="pricing-title">
            <span>${item.eyebrow}</span>
            <strong>${escapeHtml(item.name)}</strong>
          </div>
          <div class="pricing-grid">
            <label>
              Nazwa
              <input name="name" value="${escapeHtml(item.name)}" required />
            </label>
            <label>
              Cena zl
              <input name="price_pln" type="number" min="0" step="1" value="${Number(item.price_pln)}" required />
            </label>
            <label>
              Czas min
              <input name="duration_minutes" type="number" min="0" step="5" value="${Number(item.duration_minutes)}" required />
            </label>
          </div>
          <label>
            Opis
            <textarea name="description" rows="2" required>${escapeHtml(item.description)}</textarea>
          </label>
          <button class="button dark" type="submit">Zapisz cennik</button>
        </form>
      `,
    )
    .join("");
}

function renderClientWorkspace() {
  const profile = state.clientProfile || {
    name: state.user?.name || "",
    email: state.user?.email || "",
    phone: state.user?.phone || "",
    marketing_consent: false,
  };
  const form = byId("client-profile-form");
  if (!form) return;
  form.elements.name.value = profile.name || "";
  form.elements.phone.value = profile.phone || "";
  form.elements.email.value = profile.email || state.user?.email || "";
  form.elements.marketing_consent.checked = Boolean(profile.marketing_consent);

  setHtml(
    "client-vehicles-list",
    state.clientVehicles.length
      ? state.clientVehicles
          .map(
            (vehicle) => `
              <article class="vehicle-card">
                <strong>${escapeHtml([vehicle.brand, vehicle.model].filter(Boolean).join(" ") || "Auto")}</strong>
                <span>${escapeHtml(vehicle.registration_number || "brak rejestracji")} · ${vehicleSizeLabel(vehicle.vehicle_size)}</span>
                ${vehicle.color ? `<p>Kolor: ${escapeHtml(vehicle.color)}</p>` : ""}
              </article>
            `,
          )
          .join("")
      : `<p class="empty">Nie masz jeszcze zapisanego auta.</p>`,
  );

  renderClientNotifications();
}

function renderClientNotifications() {
  const summary = byId("notification-summary");
  const list = byId("client-notifications-list");
  const markAll = byId("mark-all-notifications");
  if (!summary || !list || !markAll) return;

  const notifications = state.clientNotifications?.items || [];
  const unreadCount = Number(state.clientNotifications?.unread_count || 0);
  summary.innerHTML = unreadCount
    ? `<span class="notification-count">${unreadCount} nowe</span>`
    : `<span>Brak nowych powiadomien.</span>`;
  markAll.disabled = unreadCount === 0;

  list.innerHTML = notifications.length
    ? notifications
        .map(
          (notification) => `
            <article class="notification-item ${Number(notification.is_read) ? "" : "unread"}">
              <div>
                <header>
                  <strong>${escapeHtml(notification.title)}</strong>
                  <span>${formatDate(notification.created_at)}</span>
                </header>
                <p>${escapeHtml(notification.message)}</p>
              </div>
              ${
                Number(notification.is_read)
                  ? `<span class="read-label">przeczytane</span>`
                  : `
                    <form class="notification-read-form" data-id="${notification.id}">
                      <button class="button dark" type="submit">OK</button>
                    </form>
                  `
              }
            </article>
          `,
        )
        .join("")
    : `<p class="empty">Nie masz jeszcze powiadomien.</p>`;
}

function renderRoleViews() {
  const authForms = byId("auth-forms");
  const accountCard = byId("account-card");
  const authChip = byId("auth-chip");
  const ownerStats = byId("owner-stats");
  const ownerWorkspace = byId("owner-workspace");
  const clientWorkspace = byId("client-workspace");
  const bookingForm = byId("booking-form");
  const bookingsList = byId("bookings-list");
  const panelTitle = byId("panel-title");
  const panelEyebrow = byId("panel-eyebrow");
  const bookingNavLink = byId("booking-nav-link");
  const panelNavLink = byId("panel-nav-link");
  const heroBookingAction = byId("hero-booking-action");
  const heroPanelAction = byId("hero-panel-action");

  if (state.user) {
    setHidden(authForms, true);
    setHidden(accountCard, false);
    setText("account-name", state.user.name);
    setText("account-role", `${roleLabel(state.user.role)} · ${state.user.email}`);
    const unreadText = state.user.role === "client" && Number(state.clientNotifications?.unread_count || 0)
      ? ` · ${Number(state.clientNotifications.unread_count)} nowe`
      : "";
    if (authChip) authChip.innerHTML = `
      <span>${escapeHtml(roleLabel(state.user.role))}: ${escapeHtml(state.user.name)}${escapeHtml(unreadText)}</span>
      <a href="${routeForRole(state.user.role)}">Panel</a>
    `;
  } else {
    setHidden(authForms, false);
    setHidden(accountCard, true);
    if (authChip) authChip.innerHTML = `<span>Niezalogowany</span><a href="/konto.html">Logowanie</a>`;
  }

  if (state.user?.role === "owner") {
    setText("panel-eyebrow", "Wlasciciel");
    setText("panel-title", "Wszystkie wizyty");
    setHidden(ownerStats, false);
    setHidden(ownerWorkspace, false);
    setHidden(clientWorkspace, true);
    setHidden(bookingForm, true);
    setHtml("bookings-list", bookingCards(state.bookings, { editableStatus: true }));
    if (bookingNavLink) {
      bookingNavLink.textContent = "Wizyty";
      bookingNavLink.href = "/panel-wlasciciela.html";
    }
    if (panelNavLink) {
      panelNavLink.textContent = "Panel wlasciciela";
      panelNavLink.href = "/panel-wlasciciela.html";
      panelNavLink.dataset.navPage = "owner-panel";
    }
    if (heroBookingAction) {
      heroBookingAction.textContent = "Kokpit wlasciciela";
      heroBookingAction.href = "/panel-wlasciciela.html";
    }
    if (heroPanelAction) {
      heroPanelAction.textContent = "Wszystkie wizyty";
      heroPanelAction.href = "/panel-wlasciciela.html";
    }
    renderOwnerWorkspace();
  } else if (state.user?.role === "client") {
    setText("panel-eyebrow", "Klient");
    setText("panel-title", "Moje wizyty");
    setHidden(ownerStats, true);
    setHidden(ownerWorkspace, true);
    setHidden(clientWorkspace, false);
    setHidden(bookingForm, false);
    setHtml("bookings-list", bookingCards(state.myBookings, {
      showCustomer: false,
      clientDetails: true,
      clientActions: true,
      emptyText: "Nie masz jeszcze zapisanych wizyt.",
    }));
    if (bookingNavLink) {
      bookingNavLink.textContent = "Rezerwacja";
      bookingNavLink.href = "/rezerwacja.html";
    }
    if (panelNavLink) {
      panelNavLink.textContent = "Panel klienta";
      panelNavLink.href = "/panel-klienta.html";
      panelNavLink.dataset.navPage = "client-panel";
    }
    if (heroBookingAction) {
      heroBookingAction.textContent = "Umow wizyte";
      heroBookingAction.href = "/rezerwacja.html";
    }
    if (heroPanelAction) {
      heroPanelAction.textContent = "Moje wizyty";
      heroPanelAction.href = "/panel-klienta.html";
    }
  } else {
    setText("panel-eyebrow", "Panel");
    setText("panel-title", "Plan myjni");
    setHidden(ownerStats, true);
    setHidden(ownerWorkspace, true);
    setHidden(clientWorkspace, true);
    setHidden(bookingForm, false);
    setHtml("bookings-list", `
      <div class="locked-panel">
        <strong>Panel wlasciciela</strong>
        <p>Zaloguj sie, aby zobaczyc role i przypisane widoki.</p>
      </div>
    `);
    if (bookingNavLink) {
      bookingNavLink.textContent = "Rezerwacja";
      bookingNavLink.href = "/rezerwacja.html";
    }
    if (panelNavLink) {
      panelNavLink.textContent = "Panel";
      panelNavLink.href = "/konto.html";
      panelNavLink.dataset.navPage = "client-panel";
    }
    if (heroBookingAction) {
      heroBookingAction.textContent = "Umow wizyte";
      heroBookingAction.href = "/rezerwacja.html";
    }
    if (heroPanelAction) {
      heroPanelAction.textContent = "Plan dnia";
      heroPanelAction.href = "/konto.html";
    }
  }

  if (state.user?.role === "client") {
    renderClientWorkspace();
  }
  setPageChrome();
  syncAllPanelTabs();
  syncBookingAccess();
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function vehicleSizeLabel(size) {
  const labels = {
    small: "male",
    standard: "standard",
    suv: "SUV",
    van: "van",
  };
  return labels[size] || size || "standard";
}

function selectedIds(name) {
  return [...document.querySelectorAll(`[name="${name}"]:checked`)].map((input) => Number(input.value));
}

function updateSummary() {
  const durationNode = byId("summary-duration");
  const priceNode = byId("summary-price");
  if (!durationNode || !priceNode) return;

  const serviceIds = selectedIds("service_ids");
  const addonIds = selectedIds("addon_ids");
  const selectedServices = state.services.filter((service) => serviceIds.includes(Number(service.id)));
  const selectedAddons = state.addons.filter((addon) => addonIds.includes(Number(addon.id)));

  const duration = [...selectedServices, ...selectedAddons].reduce(
    (sum, item) => sum + Number(item.duration_minutes || 0),
    0,
  );
  const total = selectedServices.reduce((sum, item) => sum + Number(item.base_price_pln || 0), 0)
    + selectedAddons.reduce((sum, item) => sum + Number(item.price_pln || 0), 0);

  durationNode.textContent = formatMinutes(duration);
  priceNode.textContent = formatMoney(total);
}

function syncBookingAccess() {
  const form = byId("booking-form");
  if (!form) return;
  const submit = form.querySelector('button[type="submit"]');
  const note = byId("booking-auth-note");
  const name = form.elements.name;
  const email = form.elements.email;
  const phone = form.elements.phone;

  name.readOnly = false;
  email.readOnly = false;
  submit.disabled = false;

  if (state.user?.role === "owner") {
    submit.disabled = true;
    if (note) note.textContent = "Konto wlasciciela pokazuje kokpit i wizyty zamiast formularza rezerwacji.";
    return;
  }

  if (!state.user) {
    submit.disabled = true;
    if (note) note.textContent = "Zaloguj sie albo utworz konto klienta przed rezerwacja.";
    return;
  }

  if (state.user.role === "client") {
    name.value = state.user.name;
    email.value = state.user.email;
    if (state.user.phone) phone.value = state.user.phone;
    name.readOnly = true;
    email.readOnly = true;
    if (note) note.textContent = "Rezerwacja zostanie zapisana na Twoim koncie klienta.";
    return;
  }

  if (note) note.textContent = "Wlasciciel moze dopisac termin klientowi.";
}

function formPayload(form) {
  const data = new FormData(form);
  return {
    starts_at: data.get("starts_at"),
    name: data.get("name"),
    phone: data.get("phone"),
    email: data.get("email"),
    brand: data.get("brand"),
    model: data.get("model"),
    registration_number: data.get("registration_number"),
    vehicle_size: data.get("vehicle_size"),
    notes: data.get("notes"),
    marketing_consent: data.get("marketing_consent") === "on",
    service_ids: selectedIds("service_ids"),
    addon_ids: selectedIds("addon_ids"),
  };
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Nie udalo sie zapisac danych.");
  }
  return data;
}

async function refreshAvailability() {
  const dateInput = byId("booking-date");
  const grid = byId("slot-grid");
  const summary = byId("slot-summary");
  if (!dateInput || !grid || !summary || !state.services.length) return;

  const serviceIds = selectedIds("service_ids");
  if (!serviceIds.length) {
    summary.textContent = "Wybierz usluge";
    grid.innerHTML = "";
    const startsAt = byId("starts-at");
    if (startsAt) startsAt.value = "";
    return;
  }

  const params = new URLSearchParams({
    date: dateInput.value,
    service_ids: serviceIds.join(","),
    addon_ids: selectedIds("addon_ids").join(","),
  });

  summary.textContent = "Sprawdzanie godzin...";
  grid.innerHTML = `<p class="empty">Sprawdzanie godzin...</p>`;

  try {
    const response = await fetch(`/api/availability?${params}`, { credentials: "same-origin" });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Nie udalo sie pobrac godzin.");
    }
    state.availability = data;
    renderAvailability();
  } catch (error) {
    state.availability = null;
    const startsAt = byId("starts-at");
    if (startsAt) startsAt.value = "";
    summary.textContent = error.message;
    grid.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

function renderAvailability() {
  const data = state.availability;
  const grid = byId("slot-grid");
  const summary = byId("slot-summary");
  const startsAt = byId("starts-at");
  if (!data || !grid || !summary || !startsAt) return;

  const workday = data.workday || {};
  if (!workday.is_open) {
    startsAt.value = "";
    summary.textContent = `${formatDay(data.date)} · zamkniete`;
    grid.innerHTML = `<p class="empty">${escapeHtml(workday.closed_reason || "Myjnia jest zamknieta w tym dniu.")}</p>`;
    return;
  }

  let selectedStartsAt = startsAt.value;
  const stillAvailable = (data.slots || []).some(
    (slot) => slot.available && slot.starts_at === selectedStartsAt,
  );
  if (selectedStartsAt && !stillAvailable) {
    startsAt.value = "";
    selectedStartsAt = "";
  }

  const availableCount = (data.slots || []).filter((slot) => slot.available).length;
  const stationText = Number(workday.station_count || 1) === 1
    ? "1 stanowisko"
    : `${Number(workday.station_count)} stanowiska`;
  summary.textContent = `${formatDay(data.date)} · ${workday.open_at}-${workday.close_at} · ${stationText} · ${formatMinutes(data.duration_minutes)} · ${availableCount} wolnych`;

  if (!data.slots?.length) {
    grid.innerHTML = `<p class="empty">Brak godzin dla tak dlugiej uslugi.</p>`;
    return;
  }

  grid.innerHTML = data.slots
    .map((slot) => {
      const selected = slot.starts_at === selectedStartsAt;
      return `
        <button
          class="slot-button ${slot.available ? "" : "unavailable"} ${selected ? "selected" : ""}"
          type="button"
          data-starts-at="${escapeHtml(slot.starts_at)}"
          ${slot.available ? "" : "disabled"}
        >
          <strong>${escapeHtml(slot.time)}</strong>
          <span>${slot.available ? `${Number(slot.remaining_capacity || 1)} wolne` : escapeHtml(slot.reason || "zajety")}</span>
        </button>
      `;
    })
    .join("");
}

async function refreshOwnerDayPlan() {
  if (state.user?.role !== "owner") return;

  const input = byId("owner-plan-date");
  if (!input?.value) return;

  try {
    const response = await fetch(`/api/owner/day-plan?date=${encodeURIComponent(input.value)}`, {
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Nie udalo sie pobrac planu dnia.");
    }
    state.ownerDayPlan = data.bookings || [];
    renderOwnerDayPlan();
  } catch (error) {
    setHtml("owner-day-plan", `<p class="empty">${escapeHtml(error.message)}</p>`);
  }
}

function schedulePayload(form) {
  return {
    station_count: Number(form.elements.station_count.value || 1),
    hours: [...document.querySelectorAll(".schedule-day-row")].map((row) => ({
      weekday: Number(row.dataset.weekday),
      is_open: Boolean(row.querySelector('[name="is_open"]')?.checked),
      opens_at: row.querySelector('[name="opens_at"]')?.value,
      closes_at: row.querySelector('[name="closes_at"]')?.value,
    })),
  };
}

async function loadBootstrap() {
  const response = await fetch("/api/bootstrap", { credentials: "same-origin" });
  const data = await response.json();
  state.services = data.services || [];
  state.addons = data.addons || [];
  state.bookings = data.bookings || [];
  state.myBookings = data.my_bookings || [];
  state.ownerDayPlan = data.owner_day_plan || [];
  state.ownerSchedule = data.owner_schedule || null;
  state.ownerMessages = data.owner_messages || [];
  state.clientProfile = data.client_profile || null;
  state.clientVehicles = data.client_vehicles || [];
  state.clientNotifications = data.client_notifications || { items: [], unread_count: 0 };
  state.dashboard = data.dashboard || {};
  state.user = data.current_user || null;

  if (enforcePageAccess()) return;

  renderSettings(data.settings || {});
  renderServices();
  renderAddons();
  renderDashboard();
  renderRoleViews();
  updateSummary();
  await refreshAvailability();
}

function setStatus(element, message, isError = false) {
  if (!element) return;
  element.classList.toggle("error", isError);
  element.textContent = message;
}

function bindForms() {
  document.addEventListener("change", (event) => {
    if (event.target.matches('[name="service_ids"], [name="addon_ids"]')) {
      updateSummary();
      void refreshAvailability();
    }

    if (event.target.matches("#booking-date")) {
      const startsAt = byId("starts-at");
      if (startsAt) startsAt.value = "";
      void refreshAvailability();
    }

    if (event.target.matches("#owner-plan-date")) {
      void refreshOwnerDayPlan();
    }

    if (event.target.matches('.schedule-day-row [name="is_open"]')) {
      syncScheduleRows();
    }
  });

  document.addEventListener("click", (event) => {
    const panelTab = event.target.closest("[data-panel-tab]");
    if (panelTab) {
      setActivePanelTab(panelTab.dataset.panelScope, panelTab.dataset.panelTab);
      return;
    }

    const stepButton = event.target.closest("[data-date-step]");
    if (stepButton) {
      const input = byId("booking-date");
      const startsAt = byId("starts-at");
      if (!input) return;
      const nextValue = addDays(input.value || input.min, Number(stepButton.dataset.dateStep || 0));
      input.value = input.min && nextValue < input.min ? input.min : nextValue;
      if (startsAt) startsAt.value = "";
      void refreshAvailability();
      return;
    }

    const slotButton = event.target.closest(".slot-button");
    if (slotButton && !slotButton.disabled) {
      const startsAt = byId("starts-at");
      if (startsAt) startsAt.value = slotButton.dataset.startsAt;
      renderAvailability();
      return;
    }

    const markAllButton = event.target.closest("#mark-all-notifications");
    if (markAllButton && !markAllButton.disabled) {
      setStatus(byId("client-notification-status"), "Oznaczanie powiadomien...");
      postJson("/api/client/notifications/read", {})
        .then((data) => {
          state.clientNotifications = data.client_notifications || state.clientNotifications;
          renderClientNotifications();
          renderRoleViews();
          setStatus(byId("client-notification-status"), "Powiadomienia oznaczone jako przeczytane.");
        })
        .catch((error) => {
          setStatus(byId("client-notification-status"), error.message, true);
        });
      return;
    }

    const socialButton = event.target.closest("[data-social-provider]");
    if (socialButton) {
      setStatus(
        byId("login-status"),
        `${socialButton.dataset.socialProvider} jest przygotowane w interfejsie. Do prawdziwego logowania potrzebne beda klucze OAuth i domena.`,
      );
    }
  });

  document.addEventListener("submit", async (event) => {
    if (event.target.matches(".booking-status-form")) {
      event.preventDefault();
      const form = event.target;
      const status = byId("owner-booking-status");
      setStatus(status, "Zapisywanie statusu...");

      try {
        const data = await postJson("/api/owner/booking-status", {
          booking_id: Number(form.dataset.bookingId),
          status: new FormData(form).get("status"),
        });
        state.bookings = data.bookings || [];
        state.dashboard = data.dashboard || {};
        renderDashboard();
        renderRoleViews();
        await refreshOwnerDayPlan();
        setStatus(byId("owner-booking-status"), "Status wizyty zapisany.");
      } catch (error) {
        setStatus(status, error.message, true);
      }
    }

    if (event.target.matches(".pricing-form")) {
      event.preventDefault();
      const form = event.target;
      const status = byId("pricing-status");
      setStatus(status, "Zapisywanie cennika...");
      const formData = new FormData(form);

      try {
        const data = await postJson("/api/owner/pricing", {
          type: form.dataset.type,
          id: Number(form.dataset.id),
          name: formData.get("name"),
          description: formData.get("description"),
          duration_minutes: Number(formData.get("duration_minutes")),
          price_pln: Number(formData.get("price_pln")),
        });
        state.services = data.services || [];
        state.addons = data.addons || [];
        renderServices();
        renderAddons();
        renderOwnerPricing();
        updateSummary();
        void refreshAvailability();
        setStatus(byId("pricing-status"), "Cennik zapisany.");
      } catch (error) {
        setStatus(status, error.message, true);
      }
    }

    if (event.target.matches("#owner-schedule-form")) {
      event.preventDefault();
      const form = event.target;
      const status = byId("owner-schedule-status");
      setStatus(status, "Zapisywanie godzin...");

      try {
        const data = await postJson("/api/owner/schedule", schedulePayload(form));
        state.ownerSchedule = data.owner_schedule || state.ownerSchedule;
        renderOwnerSchedule();
        await refreshAvailability();
        await refreshOwnerDayPlan();
        setStatus(byId("owner-schedule-status"), "Godziny pracy zapisane.");
      } catch (error) {
        setStatus(status, error.message, true);
      }
    }

    if (event.target.matches("#owner-closure-form")) {
      event.preventDefault();
      const form = event.target;
      const status = byId("owner-closure-status");
      const formData = new FormData(form);
      setStatus(status, "Dodawanie dnia wolnego...");

      try {
        const data = await postJson("/api/owner/closure", {
          date: formData.get("date"),
          reason: formData.get("reason"),
        });
        state.ownerSchedule = data.owner_schedule || state.ownerSchedule;
        form.reset();
        renderOwnerSchedule();
        await refreshAvailability();
        await refreshOwnerDayPlan();
        setStatus(byId("owner-closure-status"), "Dzien wolny dodany.");
      } catch (error) {
        setStatus(status, error.message, true);
      }
    }

    if (event.target.matches(".closure-delete-form")) {
      event.preventDefault();
      const form = event.target;
      const status = byId("owner-closure-status");
      setStatus(status, "Usuwanie dnia wolnego...");

      try {
        const data = await postJson("/api/owner/delete-closure", {
          id: Number(form.dataset.id),
        });
        state.ownerSchedule = data.owner_schedule || state.ownerSchedule;
        renderOwnerSchedule();
        await refreshAvailability();
        await refreshOwnerDayPlan();
        setStatus(byId("owner-closure-status"), "Dzien wolny usuniety.");
      } catch (error) {
        setStatus(status, error.message, true);
      }
    }

    if (event.target.matches(".client-cancel-form")) {
      event.preventDefault();
      const form = event.target;
      const status = byId("owner-booking-status");
      setStatus(status, "Odwolywanie wizyty...");

      try {
        const data = await postJson("/api/client/cancel-booking", {
          booking_id: Number(form.dataset.bookingId),
        });
        state.myBookings = data.my_bookings || [];
        state.clientNotifications = data.client_notifications || state.clientNotifications;
        renderRoleViews();
        setStatus(byId("owner-booking-status"), "Wizyta odwolana.");
      } catch (error) {
        setStatus(status, error.message, true);
      }
    }

    if (event.target.matches(".notification-read-form")) {
      event.preventDefault();
      const form = event.target;

      try {
        const data = await postJson("/api/client/notifications/read", {
          notification_id: Number(form.dataset.id),
        });
        state.clientNotifications = data.client_notifications || state.clientNotifications;
        renderClientNotifications();
        renderRoleViews();
      } catch (error) {
        setStatus(byId("client-notification-status"), error.message, true);
      }
    }
  });

  byId("client-profile-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("client-profile-status");
    setStatus(status, "Zapisywanie profilu...");
    const data = new FormData(form);

    try {
      const response = await postJson("/api/client/profile", {
        name: data.get("name"),
        phone: data.get("phone"),
        marketing_consent: data.get("marketing_consent") === "on",
      });
      state.user = response.current_user || state.user;
      state.clientProfile = response.client_profile || state.clientProfile;
      state.clientVehicles = response.client_vehicles || state.clientVehicles;
      state.myBookings = response.my_bookings || state.myBookings;
      renderRoleViews();
      setStatus(byId("client-profile-status"), "Profil zapisany.");
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });

  byId("client-vehicle-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("client-vehicle-status");
    setStatus(status, "Zapisywanie auta...");

    try {
      const response = await postJson("/api/client/vehicle", Object.fromEntries(new FormData(form).entries()));
      state.clientVehicles = response.client_vehicles || [];
      state.myBookings = response.my_bookings || state.myBookings;
      form.reset();
      form.elements.vehicle_size.value = "standard";
      renderClientWorkspace();
      renderRoleViews();
      setStatus(byId("client-vehicle-status"), "Auto zapisane.");
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });

  byId("login-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("login-status");
    setStatus(status, "Logowanie...");

    try {
      await postJson("/api/auth/login", Object.fromEntries(new FormData(form).entries()));
      setStatus(status, "Zalogowano.");
      form.reset();
      await loadBootstrap();
      redirectAfterAuth();
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });

  byId("register-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("register-status");
    setStatus(status, "Tworzenie konta...");

    try {
      await postJson("/api/auth/register", Object.fromEntries(new FormData(form).entries()));
      setStatus(status, "Konto utworzone.");
      form.reset();
      await loadBootstrap();
      redirectAfterAuth();
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });

  byId("reset-request-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("reset-request-status");
    const email = new FormData(form).get("email");
    setStatus(status, "Przygotowywanie kodu...");

    try {
      const data = await postJson("/api/auth/password-reset/request", { email });
      const completeForm = byId("reset-complete-form");
      if (completeForm) completeForm.elements.email.value = email;
      if (data.reset_token && completeForm) {
        completeForm.elements.reset_token.value = data.reset_token;
        setStatus(status, `Kod resetu: ${data.reset_token}. Wazny ${data.expires_in_minutes} min.`);
      } else {
        setStatus(status, data.message || "Jesli konto istnieje, kod zostal przygotowany.");
      }
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });

  byId("reset-complete-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("reset-complete-status");
    const formData = new FormData(form);
    setStatus(status, "Zmiana hasla...");

    try {
      const data = await postJson("/api/auth/password-reset/complete", {
        email: formData.get("email"),
        reset_token: formData.get("reset_token"),
        password: formData.get("password"),
      });
      const loginForm = byId("login-form");
      if (loginForm) loginForm.elements.email.value = formData.get("email");
      form.reset();
      setStatus(status, data.message || "Haslo zostalo zmienione.");
      setStatus(byId("login-status"), "Mozesz zalogowac sie nowym haslem.");
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });

  byId("logout-button")?.addEventListener("click", async () => {
    await postJson("/api/auth/logout", {});
    await loadBootstrap();
  });

  byId("booking-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("booking-status");
    setStatus(status, "Zapisywanie...");

    try {
      if (!form.elements.starts_at.value) {
        throw new Error("Wybierz godzine wizyty.");
      }
      const data = await postJson("/api/bookings", formPayload(form));
      setStatus(
        status,
        `Termin zapisany: ${formatDate(data.booking.starts_at)}, ${formatMoney(data.booking.total_price_pln)}.`,
      );
      form.reset();
      setDefaultBookingDate();
      if (state.services[0]) {
        const first = document.querySelector('[name="service_ids"]');
        if (first) first.checked = true;
      }
      await loadBootstrap();
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });

  byId("contact-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = byId("contact-status");
    setStatus(status, "Wysylanie...");

    try {
      const data = Object.fromEntries(new FormData(form).entries());
      await postJson("/api/contact", data);
      setStatus(status, "Wiadomosc zapisana.");
      form.reset();
    } catch (error) {
      setStatus(status, error.message, true);
    }
  });
}

async function init() {
  setPageChrome();
  setDefaultBookingDate();
  setDefaultOwnerPlanDate();
  bindForms();
  await loadBootstrap();
}

init().catch((error) => {
  setStatus(byId("booking-status"), error.message, true);
});
