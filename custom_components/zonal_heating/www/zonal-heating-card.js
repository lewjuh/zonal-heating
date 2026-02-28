const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace")
);
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

class ZonalHeatingCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _showDebug: { type: Boolean },
    };
  }

  constructor() {
    super();
    this._showDebug = false;
  }

  static getConfigElement() {
    return document.createElement("zonal-heating-card-editor");
  }

  static getStubConfig() {
    return { zone_sensor: "", show_debug: false };
  }

  setConfig(config) {
    if (!config.zone_sensor) {
      throw new Error("Please define a zone_sensor");
    }
    this.config = config;
    this._showDebug = config.show_debug || false;
  }

  getCardSize() {
    return 3;
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      ha-card {
        padding: 16px;
        overflow: hidden;
      }

      /* ---- Card Header ---- */
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
      }
      .card-title {
        font-size: 1.1em;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      /* ---- Zone Banner ---- */
      .zone-banner {
        display: flex;
        align-items: center;
        padding: 16px;
        border-radius: 12px;
        margin-bottom: 14px;
        gap: 14px;
      }
      .zone-banner.heating {
        background: linear-gradient(
          135deg,
          rgba(255, 152, 0, 0.18) 0%,
          rgba(255, 87, 34, 0.18) 100%
        );
        border: 1.5px solid rgba(255, 152, 0, 0.4);
      }
      .zone-banner.idle {
        background: linear-gradient(
          135deg,
          rgba(76, 175, 80, 0.12) 0%,
          rgba(0, 150, 136, 0.12) 100%
        );
        border: 1.5px solid rgba(76, 175, 80, 0.3);
      }
      .zone-banner.unavailable {
        background: rgba(158, 158, 158, 0.12);
        border: 1.5px solid rgba(158, 158, 158, 0.3);
      }

      .zone-icon {
        width: 42px;
        height: 42px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
        flex-shrink: 0;
      }
      .zone-icon ha-icon {
        --mdc-icon-size: 24px;
        width: 24px;
        height: 24px;
      }
      .zone-icon.heating {
        background: rgba(255, 152, 0, 0.25);
        color: var(--warning-color, #ff9800);
      }
      .zone-icon.idle {
        background: rgba(76, 175, 80, 0.2);
        color: var(--success-color, #4caf50);
      }
      .zone-icon.unavailable {
        background: rgba(158, 158, 158, 0.2);
        color: var(--disabled-color, #9e9e9e);
      }

      .zone-info {
        flex: 1;
        min-width: 0;
      }
      .zone-state {
        font-size: 1.05em;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .zone-state.heating {
        color: var(--warning-color, #ff9800);
      }
      .zone-state.idle {
        color: var(--success-color, #4caf50);
      }
      .zone-state.unavailable {
        color: var(--disabled-color, #9e9e9e);
      }
      .zone-summary {
        font-size: 0.85em;
        color: var(--secondary-text-color);
        margin-top: 2px;
      }
      .zone-temp {
        font-size: 1.4em;
        font-weight: 700;
        flex-shrink: 0;
        color: var(--primary-text-color);
      }

      /* ---- Alert Chips ---- */
      .alerts {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 14px;
      }
      .alert-chip {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 5px 10px;
        border-radius: 16px;
        font-size: 0.78em;
        font-weight: 500;
      }
      .alert-chip ha-icon {
        --mdc-icon-size: 14px;
        width: 14px;
        height: 14px;
      }
      .alert-chip.warning {
        background: rgba(255, 152, 0, 0.12);
        color: var(--warning-color, #ff9800);
        border: 1px solid rgba(255, 152, 0, 0.3);
      }
      .alert-chip.info {
        background: rgba(33, 150, 243, 0.12);
        color: var(--info-color, #2196f3);
        border: 1px solid rgba(33, 150, 243, 0.3);
      }
      .alert-chip.neutral {
        background: rgba(158, 158, 158, 0.1);
        color: var(--secondary-text-color);
        border: 1px solid var(--divider-color);
      }
      .alert-chip.success {
        background: rgba(76, 175, 80, 0.12);
        color: var(--success-color, #4caf50);
        border: 1px solid rgba(76, 175, 80, 0.3);
      }

      /* ---- Room Cards ---- */
      .rooms {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .room {
        display: flex;
        align-items: center;
        padding: 14px 16px;
        border-radius: 10px;
        gap: 12px;
      }
      .room.needs-heat {
        background: rgba(255, 152, 0, 0.1);
        border: 1px solid rgba(255, 152, 0, 0.25);
      }
      .room.satisfied {
        background: rgba(76, 175, 80, 0.06);
        border: 1px solid rgba(76, 175, 80, 0.15);
      }
      .room.window-open {
        background: rgba(33, 150, 243, 0.08);
        border: 1px solid rgba(33, 150, 243, 0.2);
      }
      .room.off {
        background: rgba(158, 158, 158, 0.06);
        border: 1px solid rgba(158, 158, 158, 0.15);
        opacity: 0.65;
      }

      .room-indicator {
        width: 34px;
        height: 34px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
        flex-shrink: 0;
      }
      .room-indicator ha-icon {
        --mdc-icon-size: 18px;
        width: 18px;
        height: 18px;
      }
      .room-indicator.needs-heat {
        background: rgba(255, 152, 0, 0.2);
        color: var(--warning-color, #ff9800);
      }
      .room-indicator.satisfied {
        background: rgba(76, 175, 80, 0.2);
        color: var(--success-color, #4caf50);
      }
      .room-indicator.window-open {
        background: rgba(33, 150, 243, 0.2);
        color: var(--info-color, #2196f3);
      }
      .room-indicator.off {
        background: rgba(158, 158, 158, 0.15);
        color: var(--disabled-color, #9e9e9e);
      }

      .room-body {
        flex: 1;
        min-width: 0;
      }
      .room-name-row {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .room-name {
        font-size: 0.95em;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .room-status-badge {
        font-size: 0.65em;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 2px 7px;
        border-radius: 4px;
        flex-shrink: 0;
        white-space: nowrap;
      }
      .room-status-badge.needs-heat {
        background: rgba(255, 152, 0, 0.2);
        color: var(--warning-color, #ff9800);
      }
      .room-status-badge.satisfied {
        background: rgba(76, 175, 80, 0.15);
        color: var(--success-color, #4caf50);
      }
      .room-status-badge.window-open {
        background: rgba(33, 150, 243, 0.15);
        color: var(--info-color, #2196f3);
      }
      .room-status-badge.off {
        background: rgba(158, 158, 158, 0.12);
        color: var(--disabled-color, #9e9e9e);
      }

      .room-reason {
        font-size: 0.78em;
        color: var(--secondary-text-color);
        margin-top: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .room-temps {
        text-align: right;
        flex-shrink: 0;
      }
      .room-current-temp {
        font-size: 1.5em;
        font-weight: 700;
        line-height: 1.1;
        color: var(--primary-text-color);
      }
      .room.needs-heat .room-current-temp {
        color: var(--warning-color, #ff9800);
      }
      .room.window-open .room-current-temp {
        color: var(--info-color, #2196f3);
      }
      .room-target-temp {
        font-size: 0.8em;
        color: var(--secondary-text-color);
        margin-top: 2px;
      }
      .room-deficit {
        font-size: 0.75em;
        font-weight: 600;
        color: var(--warning-color, #ff9800);
        margin-top: 1px;
      }

      /* ---- Debug ---- */
      .debug-toggle {
        cursor: pointer;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.75em;
        background: var(--divider-color);
        color: var(--secondary-text-color);
        transition: background-color 0.2s;
        user-select: none;
      }
      .debug-toggle:hover {
        background: var(--secondary-background-color);
      }
      .debug-section {
        margin-top: 14px;
        padding: 12px;
        background: var(--secondary-background-color);
        border-radius: 8px;
        font-family: monospace;
        font-size: 0.72em;
      }
      .debug-title {
        font-weight: 600;
        margin-bottom: 8px;
        font-size: 1.1em;
      }
      .debug-item {
        display: flex;
        justify-content: space-between;
        padding: 3px 0;
        border-bottom: 1px solid var(--divider-color);
      }
      .debug-item:last-child {
        border-bottom: none;
      }
      .debug-key {
        color: var(--secondary-text-color);
      }
      .debug-value {
        font-weight: 500;
      }
      .debug-value.true {
        color: var(--success-color, #4caf50);
      }
      .debug-value.false {
        color: var(--error-color, #f44336);
      }
    `;
  }

  render() {
    if (!this.hass || !this.config) return html``;

    const zoneSensor = this.hass.states[this.config.zone_sensor];
    if (!zoneSensor) {
      return html`
        <ha-card>
          <div class="card-header">
            <span class="card-title"
              >${this.config.title || "Zonal Heating"}</span
            >
          </div>
          <div>Zone sensor not found: ${this.config.zone_sensor}</div>
        </ha-card>
      `;
    }

    const state = zoneSensor.state;
    const attrs = zoneSensor.attributes;

    return html`
      <ha-card>
        <div class="card-header">
          <span class="card-title"
            >${this.config.title ||
            attrs.zone_climate ||
            "Zonal Heating"}</span
          >
          <span class="debug-toggle" @click=${this._toggleDebug}>
            ${this._showDebug ? "Hide Debug" : "Debug"}
          </span>
        </div>

        ${this._renderZoneBanner(state, attrs)}
        ${this._renderAlerts(attrs)}

        <div class="rooms">
          ${this._renderRooms(attrs)}
        </div>

        ${this._showDebug ? this._renderDebug(attrs) : ""}
      </ha-card>
    `;
  }

  _renderZoneBanner(state, attrs) {
    const icons = {
      heating: "mdi:fire",
      idle: "mdi:check-circle",
      unavailable: "mdi:alert-circle",
    };
    const labels = {
      heating: "Heating",
      idle: "Idle",
      unavailable: "Unavailable",
    };

    const detailedRooms = attrs.detailed_rooms || [];
    const needingHeat = detailedRooms.filter((r) => r.needs_heat && r.is_on);
    const totalRooms = detailedRooms.length;

    let summary = "";
    if (state === "heating") {
      if (needingHeat.length === 0) {
        summary = "Waiting to turn off (all rooms satisfied)";
      } else if (needingHeat.length <= 3) {
        summary = needingHeat.map((r) => r.name).join(", ");
      } else {
        summary = `${needingHeat.length} of ${totalRooms} rooms calling for heat`;
      }
    } else if (state === "idle") {
      summary =
        totalRooms > 0
          ? "All rooms at target temperature"
          : "No rooms configured";
    } else {
      summary = "Zone thermostat unavailable";
    }

    const zoneTemp = attrs.zone_current_temp;

    return html`
      <div class="zone-banner ${state}">
        <div class="zone-icon ${state}">
          <ha-icon icon="${icons[state] || "mdi:thermostat"}"></ha-icon>
        </div>
        <div class="zone-info">
          <div class="zone-state ${state}">${labels[state] || state}</div>
          <div class="zone-summary">${summary}</div>
        </div>
        ${zoneTemp != null
          ? html`<span class="zone-temp"
              >${Number(zoneTemp).toFixed(1)}°</span
            >`
          : ""}
      </div>
    `;
  }

  _renderAlerts(attrs) {
    const chips = [];
    const rooms = attrs.detailed_rooms || [];

    if (attrs.cycle_time_blocking) {
      const t = attrs.time_until_cycle_allowed_minutes;
      chips.push(html`
        <span class="alert-chip warning">
          <ha-icon icon="mdi:timer-sand"></ha-icon>
          Cycle cooldown${t ? ` (${t.toFixed(1)} min)` : ""}
        </span>
      `);
    }

    if (attrs.startup_grace_period) {
      chips.push(html`
        <span class="alert-chip success">
          <ha-icon icon="mdi:rocket-launch"></ha-icon>
          Startup grace
        </span>
      `);
    }

    const windowRooms = rooms.filter(
      (r) => r.window_confirmed || r.window_open
    );
    if (windowRooms.length > 0) {
      chips.push(html`
        <span
          class="alert-chip info"
          title="${windowRooms.map((r) => r.name).join(", ")}"
        >
          <ha-icon icon="mdi:window-open-variant"></ha-icon>
          ${windowRooms.length} window${windowRooms.length > 1 ? "s" : ""} open
        </span>
      `);
    }

    const offRooms = rooms.filter((r) => !r.is_on);
    if (offRooms.length > 0) {
      chips.push(html`
        <span
          class="alert-chip neutral"
          title="${offRooms.map((r) => r.name).join(", ")}"
        >
          <ha-icon icon="mdi:power-off"></ha-icon>
          ${offRooms.length} room${offRooms.length > 1 ? "s" : ""} off
        </span>
      `);
    }

    if (chips.length === 0) return html``;
    return html`<div class="alerts">${chips}</div>`;
  }

  _renderRooms(attrs) {
    const rooms = attrs.detailed_rooms || [];
    if (rooms.length === 0) return html`<div>No rooms configured</div>`;
    return rooms.map((room) => this._renderRoom(room));
  }

  _renderRoom(room) {
    let status = "satisfied";
    let icon = "mdi:thermometer-check";
    let statusLabel = "At target";

    if (!room.is_on) {
      status = "off";
      icon = "mdi:power-off";
      statusLabel = "Off";
    } else if (room.window_confirmed || room.window_open) {
      status = "window-open";
      icon = "mdi:window-open-variant";
      statusLabel = room.window_confirmed ? "Window open" : "Detecting";
    } else if (room.needs_heat) {
      status = "needs-heat";
      icon = "mdi:fire";
      statusLabel = "Calling";
    }

    const currentTemp =
      room.current_temp != null ? Number(room.current_temp).toFixed(1) : "--";
    const targetTemp =
      room.target_temp != null ? Number(room.target_temp).toFixed(1) : "--";
    const deficit = room.deficit || 0;

    return html`
      <div class="room ${status}">
        <div class="room-indicator ${status}">
          <ha-icon icon="${icon}"></ha-icon>
        </div>
        <div class="room-body">
          <div class="room-name-row">
            <span class="room-name">${room.name || "Unknown"}</span>
            <span class="room-status-badge ${status}">${statusLabel}</span>
          </div>
          <div class="room-reason">${this._getRoomReason(room)}</div>
        </div>
        <div class="room-temps">
          <div class="room-current-temp">${currentTemp}°</div>
          <div class="room-target-temp">Target ${targetTemp}°</div>
          ${deficit > 0
            ? html`<div class="room-deficit">
                ${deficit.toFixed(1)}° below
              </div>`
            : ""}
        </div>
      </div>
    `;
  }

  _getRoomReason(room) {
    if (!room.is_on) return "Climate entity is off";
    if (room.window_confirmed) return "Window confirmed open - heat paused";
    if (room.window_open) return "Window detected - confirming...";
    if (room.needs_heat) {
      const deficit = room.deficit || 0;
      return `${deficit.toFixed(1)}° below heating threshold`;
    }
    return "Temperature at or above target";
  }

  _renderDebug(attrs) {
    const items = [
      { key: "zone_is_on", value: attrs.zone_is_on },
      { key: "min_cycle_time", value: `${attrs.min_cycle_time_minutes} min` },
      {
        key: "time_since_change",
        value:
          attrs.time_since_last_change_minutes != null
            ? `${attrs.time_since_last_change_minutes} min`
            : "N/A",
      },
      { key: "cycle_blocking", value: attrs.cycle_time_blocking },
      { key: "retry_timer", value: attrs.retry_timer_active },
      { key: "rooms_needing_heat", value: attrs.rooms_needing_heat_count },
    ];

    return html`
      <div class="debug-section">
        <div class="debug-title">Zone Debug</div>
        ${items.map(
          (item) => html`
            <div class="debug-item">
              <span class="debug-key">${item.key}</span>
              <span
                class="debug-value ${typeof item.value === "boolean"
                  ? item.value
                  : ""}"
                >${this._formatDebugValue(item.value)}</span
              >
            </div>
          `
        )}
      </div>
    `;
  }

  _formatDebugValue(value) {
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (value == null) return "N/A";
    return value;
  }

  _toggleDebug() {
    this._showDebug = !this._showDebug;
    this.requestUpdate();
  }
}

class ZonalHeatingCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _config: { type: Object },
    };
  }

  setConfig(config) {
    this._config = config;
  }

  static get styles() {
    return css`
      .form-row {
        margin-bottom: 16px;
      }
      .form-row label {
        display: block;
        margin-bottom: 4px;
        font-weight: 500;
      }
      .form-row input,
      .form-row select {
        width: 100%;
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background-color: var(--card-background-color);
        color: var(--primary-text-color);
      }
      .helper-text {
        font-size: 0.85em;
        color: var(--secondary-text-color);
        margin-top: 4px;
      }
    `;
  }

  render() {
    if (!this.hass || !this._config) return html``;

    const zoneSensors = Object.keys(this.hass.states)
      .filter(
        (e) =>
          e.startsWith("sensor.zonal_heating_") && e.endsWith("_status")
      )
      .sort();

    return html`
      <div class="form-row">
        <label>Title (optional)</label>
        <input
          type="text"
          .value=${this._config.title || ""}
          @input=${(e) => this._valueChanged("title", e.target.value)}
        />
      </div>
      <div class="form-row">
        <label>Zone Sensor</label>
        <select
          .value=${this._config.zone_sensor || ""}
          @change=${(e) => this._valueChanged("zone_sensor", e.target.value)}
        >
          <option value="">Select a zone sensor...</option>
          ${zoneSensors.map(
            (sensor) =>
              html`<option
                value="${sensor}"
                ?selected=${this._config.zone_sensor === sensor}
              >
                ${sensor}
              </option>`
          )}
        </select>
        <div class="helper-text">
          Select the zone diagnostic sensor (e.g.,
          sensor.zonal_heating_main_zone_status)
        </div>
      </div>
      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${this._config.show_debug || false}
            @change=${(e) =>
              this._valueChanged("show_debug", e.target.checked)}
          />
          Show debug info by default
        </label>
      </div>
    `;
  }

  _valueChanged(key, value) {
    if (!this._config) return;
    const newConfig = { ...this._config, [key]: value };
    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }
}

if (!customElements.get("zonal-heating-card")) {
  customElements.define("zonal-heating-card", ZonalHeatingCard);
}
if (!customElements.get("zonal-heating-card-editor")) {
  customElements.define("zonal-heating-card-editor", ZonalHeatingCardEditor);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "zonal-heating-card",
  name: "Zonal Heating Card",
  description:
    "A card for displaying zonal heating status and room information",
  preview: true,
  documentationURL: "https://github.com/lewjuh/zonal-heating",
});

console.info(
  "%c ZONAL-HEATING-CARD %c v2.1.0 ",
  "color: white; background: #ff9800; font-weight: bold;",
  "color: #ff9800; background: white; font-weight: bold;"
);
