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
    return {
      zone_sensor: "",
      room_sensors: [],
      climate_entities: [],
      show_debug: false,
    };
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
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
      }
      .title {
        font-size: 1.1em;
        font-weight: 500;
      }
      .zone-status {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        border-radius: 8px;
        margin-bottom: 12px;
      }
      .zone-status.heating {
        background-color: rgba(255, 152, 0, 0.15);
        border: 1px solid var(--warning-color, #ff9800);
      }
      .zone-status.idle {
        background-color: rgba(76, 175, 80, 0.15);
        border: 1px solid var(--success-color, #4caf50);
      }
      .zone-status.away_mode,
      .zone-status.away_pending {
        background-color: rgba(33, 150, 243, 0.15);
        border: 1px solid var(--info-color, #2196f3);
      }
      .zone-status.unavailable {
        background-color: rgba(158, 158, 158, 0.15);
        border: 1px solid var(--disabled-color, #9e9e9e);
      }
      .status-icon {
        --mdc-icon-size: 20px;
        width: 20px;
        height: 20px;
      }
      .status-icon.heating {
        color: var(--warning-color, #ff9800);
      }
      .status-icon.idle {
        color: var(--success-color, #4caf50);
      }
      .status-icon.away_mode,
      .status-icon.away_pending {
        color: var(--info-color, #2196f3);
      }
      .zone-info {
        flex: 1;
        min-width: 0;
      }
      .zone-state {
        font-size: 0.95em;
        font-weight: 500;
        text-transform: capitalize;
      }
      .zone-reason {
        font-size: 0.8em;
        color: var(--secondary-text-color);
        margin-top: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .zone-temp {
        font-size: 1.1em;
        font-weight: 500;
        white-space: nowrap;
      }
      .zone-meta {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 4px;
      }
      .people-badge {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        font-size: 0.75em;
        color: var(--secondary-text-color);
        background-color: var(--divider-color);
        padding: 2px 6px;
        border-radius: 10px;
      }
      .people-badge ha-icon {
        --mdc-icon-size: 12px;
        width: 12px;
        height: 12px;
      }
      .rooms-container {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .room-card {
        display: flex;
        align-items: center;
        padding: 8px 10px;
        background-color: var(--card-background-color);
        border-radius: 6px;
        border: 1px solid var(--divider-color);
      }
      .room-card.needs-heat {
        border-left: 3px solid var(--warning-color, #ff9800);
      }
      .room-card.satisfied {
        border-left: 3px solid var(--success-color, #4caf50);
      }
      .room-card.window-open {
        border-left: 3px solid var(--info-color, #2196f3);
      }
      .room-card.overheated {
        border-left: 3px solid var(--error-color, #f44336);
      }
      .room-card.off {
        border-left: 3px solid var(--disabled-color, #9e9e9e);
        opacity: 0.7;
      }
      .room-icon {
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
        margin-right: 10px;
        flex-shrink: 0;
      }
      .room-icon ha-icon {
        --mdc-icon-size: 16px;
        width: 16px;
        height: 16px;
      }
      .room-icon.needs-heat {
        background-color: rgba(255, 152, 0, 0.2);
        color: var(--warning-color, #ff9800);
      }
      .room-icon.satisfied {
        background-color: rgba(76, 175, 80, 0.2);
        color: var(--success-color, #4caf50);
      }
      .room-icon.window-open {
        background-color: rgba(33, 150, 243, 0.2);
        color: var(--info-color, #2196f3);
      }
      .room-icon.overheated {
        background-color: rgba(244, 67, 54, 0.2);
        color: var(--error-color, #f44336);
      }
      .room-icon.off {
        background-color: rgba(158, 158, 158, 0.2);
        color: var(--disabled-color, #9e9e9e);
      }
      .room-info {
        flex: 1;
        min-width: 0;
      }
      .room-name {
        font-size: 0.9em;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .room-temps {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 0.8em;
        color: var(--secondary-text-color);
        margin-top: 1px;
      }
      .room-temps ha-icon {
        --mdc-icon-size: 12px;
        width: 12px;
        height: 12px;
        opacity: 0.6;
      }
      .current-temp {
        font-weight: 500;
        color: var(--primary-text-color);
      }
      .temp-deficit {
        color: var(--warning-color);
        font-size: 0.9em;
      }
      .room-reason {
        font-size: 0.75em;
        color: var(--secondary-text-color);
        margin-top: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .debug-toggle {
        cursor: pointer;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.75em;
        background-color: var(--divider-color);
        transition: background-color 0.2s;
      }
      .debug-toggle:hover {
        background-color: var(--secondary-background-color);
      }
      .debug-section {
        margin-top: 12px;
        padding: 10px;
        background-color: var(--secondary-background-color);
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.7em;
      }
      .debug-title {
        font-weight: 600;
        margin-bottom: 6px;
        color: var(--primary-text-color);
        font-size: 1.1em;
      }
      .debug-item {
        display: flex;
        justify-content: space-between;
        padding: 2px 0;
        border-bottom: 1px solid var(--divider-color);
      }
      .debug-item:last-child {
        border-bottom: none;
      }
      .debug-key {
        color: var(--secondary-text-color);
      }
      .debug-value {
        color: var(--primary-text-color);
        font-weight: 500;
      }
      .debug-value.true {
        color: var(--success-color, #4caf50);
      }
      .debug-value.false {
        color: var(--error-color, #f44336);
      }
      .divider {
        height: 1px;
        background-color: var(--divider-color);
        margin: 10px 0;
      }
    `;
  }

  render() {
    if (!this.hass || !this.config) {
      return html``;
    }

    const zoneSensor = this.hass.states[this.config.zone_sensor];
    if (!zoneSensor) {
      return html`
        <ha-card>
          <div class="header">
            <span class="title">${this.config.title || "Zonal Heating"}</span>
          </div>
          <div>Zone sensor not found: ${this.config.zone_sensor}</div>
        </ha-card>
      `;
    }

    const zoneState = zoneSensor.state;
    const zoneAttrs = zoneSensor.attributes;

    return html`
      <ha-card>
        <div class="header">
          <span class="title">${this.config.title || zoneAttrs.zone_climate || "Zonal Heating"}</span>
          <span class="debug-toggle" @click=${this._toggleDebug}>
            ${this._showDebug ? "Hide Debug" : "Debug"}
          </span>
        </div>

        ${this._renderZoneStatus(zoneState, zoneAttrs)}

        <div class="divider"></div>

        <div class="rooms-container">
          ${this._renderRooms(zoneAttrs)}
        </div>

        ${this._showDebug ? this._renderDebug(zoneAttrs) : ""}
      </ha-card>
    `;
  }

  _renderZoneStatus(state, attrs) {
    const iconMap = {
      heating: "mdi:fire",
      idle: "mdi:check-circle",
      away_mode: "mdi:home-export-outline",
      away_pending: "mdi:timer-sand",
      unavailable: "mdi:alert-circle",
    };

    const stateLabels = {
      heating: "Heating Active",
      idle: "Idle",
      away_mode: "Away Mode",
      away_pending: "Away Pending",
      unavailable: "Unavailable",
    };

    return html`
      <div class="zone-status ${state}">
        <ha-icon class="status-icon ${state}" icon="${iconMap[state] || "mdi:thermostat"}"></ha-icon>
        <div class="zone-info">
          <div class="zone-state">${stateLabels[state] || state}</div>
          <div class="zone-reason">${attrs.reason || ""}</div>
          ${attrs.people_tracked > 0
            ? html`
                <div class="zone-meta">
                  <span class="people-badge">
                    <ha-icon icon="mdi:account-group"></ha-icon>
                    ${attrs.people_home || 0}/${attrs.people_tracked}
                  </span>
                </div>
              `
            : ""}
        </div>
        ${attrs.zone_current_temp
          ? html`<span class="zone-temp">${attrs.zone_current_temp.toFixed(1)}°C</span>`
          : ""}
      </div>
    `;
  }

  _renderRooms(zoneAttrs) {
    const detailedRooms = zoneAttrs.detailed_rooms || [];
    const roomSensors = this.config.room_sensors || [];

    if (detailedRooms.length === 0 && roomSensors.length === 0) {
      return html`<div>No rooms configured</div>`;
    }

    if (detailedRooms.length > 0) {
      return detailedRooms.map((room) => this._renderRoomFromZoneData(room));
    }

    return roomSensors.map((sensorId) => {
      const sensor = this.hass.states[sensorId];
      if (!sensor) return html``;
      return this._renderRoomFromSensor(sensor);
    });
  }

  _renderRoomFromZoneData(room) {
    let status = "satisfied";
    let icon = "mdi:thermometer";

    if (!room.is_on) {
      status = "off";
      icon = "mdi:power-off";
    } else if (room.overheated) {
      status = "overheated";
      icon = "mdi:thermometer-alert";
    } else if (room.window_confirmed || room.window_open) {
      status = "window-open";
      icon = "mdi:window-open-variant";
    } else if (room.needs_heat) {
      status = "needs-heat";
      icon = "mdi:fire";
    }

    const currentTemp = room.current_temp !== null ? room.current_temp.toFixed(1) : "--";
    const targetTemp = room.target_temp !== null ? room.target_temp.toFixed(1) : "--";

    return html`
      <div class="room-card ${status}">
        <div class="room-icon ${status}">
          <ha-icon icon="${icon}"></ha-icon>
        </div>
        <div class="room-info">
          <div class="room-name">${room.name}</div>
          <div class="room-temps">
            <span class="current-temp">${currentTemp}°C</span>
            <ha-icon icon="mdi:arrow-right"></ha-icon>
            <span>${targetTemp}°C</span>
            ${room.deficit > 0 ? html`<span class="temp-deficit">(−${room.deficit.toFixed(1)}°)</span>` : ""}
          </div>
          <div class="room-reason">${this._getRoomReason(room)}</div>
        </div>
      </div>
    `;
  }

  _renderRoomFromSensor(sensor) {
    const attrs = sensor.attributes;
    const state = sensor.state;

    let status = "satisfied";
    let icon = "mdi:thermometer";

    if (state === "off") {
      status = "off";
      icon = "mdi:power-off";
    } else if (state === "overheated") {
      status = "overheated";
      icon = "mdi:thermometer-alert";
    } else if (state === "window_open") {
      status = "window-open";
      icon = "mdi:window-open-variant";
    } else if (state === "needs_heat") {
      status = "needs-heat";
      icon = "mdi:fire";
    }

    const currentTemp = attrs.current_temp !== null ? attrs.current_temp.toFixed(1) : "--";
    const targetTemp = attrs.target_temp !== null ? attrs.target_temp.toFixed(1) : "--";

    return html`
      <div class="room-card ${status}">
        <div class="room-icon ${status}">
          <ha-icon icon="${icon}"></ha-icon>
        </div>
        <div class="room-info">
          <div class="room-name">${sensor.attributes.friendly_name || sensor.entity_id}</div>
          <div class="room-temps">
            <span class="current-temp">${currentTemp}°C</span>
            <ha-icon icon="mdi:arrow-right"></ha-icon>
            <span>${targetTemp}°C</span>
          </div>
          <div class="room-reason">${attrs.reason || ""}</div>
        </div>
      </div>
    `;
  }

  _getRoomReason(room) {
    if (!room.is_on) return "Climate entity is off";
    if (room.overheated) return `Overheated - temp above limit`;
    if (room.window_confirmed) return "Window confirmed open";
    if (room.window_open) return "Window detected - waiting to confirm";
    if (room.needs_heat) return `Needs heat - ${room.deficit.toFixed(1)}°C below threshold`;
    return "Temperature satisfied";
  }

  _renderDebug(attrs) {
    const debugItems = [
      { key: "zone_is_on", value: attrs.zone_is_on },
      { key: "min_cycle_time", value: `${attrs.min_cycle_time_minutes} min` },
      { key: "time_since_change", value: attrs.time_since_last_change_minutes ? `${attrs.time_since_last_change_minutes} min` : "N/A" },
      { key: "cycle_blocking", value: attrs.cycle_time_blocking },
      { key: "retry_timer", value: attrs.retry_timer_active },
      { key: "away_mode", value: attrs.away_mode },
      { key: "away_pending", value: attrs.away_mode_pending },
      { key: "rooms_needing_heat", value: attrs.rooms_needing_heat_count },
    ];

    return html`
      <div class="debug-section">
        <div class="debug-title">Zone Debug Info</div>
        ${debugItems.map(
          (item) => html`
            <div class="debug-item">
              <span class="debug-key">${item.key}</span>
              <span class="debug-value ${typeof item.value === "boolean" ? item.value : ""}">${this._formatDebugValue(item.value)}</span>
            </div>
          `
        )}
      </div>
    `;
  }

  _formatDebugValue(value) {
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (value === null || value === undefined) return "N/A";
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
    if (!this.hass || !this._config) {
      return html``;
    }

    const zoneSensors = Object.keys(this.hass.states)
      .filter((e) => e.startsWith("sensor.zonal_heating_") && e.endsWith("_status"))
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
            (sensor) => html`<option value="${sensor}" ?selected=${this._config.zone_sensor === sensor}>${sensor}</option>`
          )}
        </select>
        <div class="helper-text">Select the zone diagnostic sensor (e.g., sensor.zonal_heating_main_zone_status)</div>
      </div>
      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${this._config.show_debug || false}
            @change=${(e) => this._valueChanged("show_debug", e.target.checked)}
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

    const event = new CustomEvent("config-changed", {
      detail: { config: newConfig },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

customElements.define("zonal-heating-card", ZonalHeatingCard);
customElements.define("zonal-heating-card-editor", ZonalHeatingCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "zonal-heating-card",
  name: "Zonal Heating Card",
  description: "A card for displaying zonal heating status and room information",
  preview: true,
  documentationURL: "https://github.com/lewjuh/zonal-heating",
});

console.info(
  "%c ZONAL-HEATING-CARD %c v1.1.0 ",
  "color: white; background: #ff9800; font-weight: bold;",
  "color: #ff9800; background: white; font-weight: bold;"
);
