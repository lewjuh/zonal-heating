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
      _scheduleModalOpen: { type: Boolean },
      _selectedRoom: { type: String },
      _editingSchedule: { type: Object },
      _activeTab: { type: String },
      _addingPoint: { type: Boolean },
      _newPointTime: { type: String },
      _newPointTemp: { type: Number },
    };
  }

  constructor() {
    super();
    this._showDebug = false;
    this._scheduleModalOpen = false;
    this._selectedRoom = null;
    this._editingSchedule = null;
    this._activeTab = "weekday";
    this._addingPoint = false;
    this._newPointTime = "08:00";
    this._newPointTemp = 20;
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
      .status-indicators {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 10px;
      }
      .status-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 0.75em;
        font-weight: 500;
      }
      .status-chip ha-icon {
        --mdc-icon-size: 14px;
        width: 14px;
        height: 14px;
      }
      .status-chip.blocking {
        background-color: rgba(255, 152, 0, 0.15);
        color: var(--warning-color, #ff9800);
        border: 1px solid var(--warning-color, #ff9800);
      }
      .status-chip.info {
        background-color: rgba(33, 150, 243, 0.15);
        color: var(--info-color, #2196f3);
        border: 1px solid var(--info-color, #2196f3);
      }
      .status-chip.error {
        background-color: rgba(244, 67, 54, 0.15);
        color: var(--error-color, #f44336);
        border: 1px solid var(--error-color, #f44336);
      }
      .status-chip.success {
        background-color: rgba(76, 175, 80, 0.15);
        color: var(--success-color, #4caf50);
        border: 1px solid var(--success-color, #4caf50);
      }
      .status-chip.neutral {
        background-color: rgba(158, 158, 158, 0.15);
        color: var(--secondary-text-color);
        border: 1px solid var(--divider-color);
      }
      .room-actions {
        display: flex;
        align-items: center;
        gap: 4px;
        margin-left: 8px;
      }
      .schedule-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: none;
        background-color: var(--divider-color);
        cursor: pointer;
        transition: background-color 0.2s;
      }
      .schedule-btn:hover {
        background-color: var(--primary-color);
      }
      .schedule-btn ha-icon {
        --mdc-icon-size: 16px;
        width: 16px;
        height: 16px;
        color: var(--primary-text-color);
      }
      .schedule-btn:hover ha-icon {
        color: var(--text-primary-color);
      }
      .schedule-btn.active {
        background-color: var(--primary-color);
      }
      .schedule-btn.active ha-icon {
        color: var(--text-primary-color);
      }
      .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: rgba(0, 0, 0, 0.6);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 999;
      }
      .modal-content {
        background-color: var(--card-background-color);
        border-radius: 12px;
        width: 90%;
        max-width: 500px;
        max-height: 85vh;
        overflow-y: auto;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      }
      .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px;
        border-bottom: 1px solid var(--divider-color);
      }
      .modal-title {
        font-size: 1.2em;
        font-weight: 500;
      }
      .modal-close {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        border: none;
        background: transparent;
        cursor: pointer;
      }
      .modal-close:hover {
        background-color: var(--divider-color);
      }
      .modal-close ha-icon {
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      .modal-body {
        padding: 16px;
      }
      .schedule-toggle {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px;
        background-color: var(--secondary-background-color);
        border-radius: 8px;
        margin-bottom: 16px;
      }
      .schedule-toggle-label {
        font-weight: 500;
      }
      .schedule-toggle input[type="checkbox"] {
        width: 40px;
        height: 20px;
        cursor: pointer;
      }
      .tab-container {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
      }
      .tab-btn {
        flex: 1;
        padding: 10px;
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        background-color: transparent;
        cursor: pointer;
        font-size: 0.9em;
        color: var(--primary-text-color);
        transition: all 0.2s;
      }
      .tab-btn.active {
        background-color: var(--primary-color);
        color: var(--text-primary-color);
        border-color: var(--primary-color);
      }
      .timeline-container {
        margin-bottom: 16px;
      }
      .timeline-header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 8px;
        font-size: 0.75em;
        color: var(--secondary-text-color);
      }
      .timeline {
        position: relative;
        height: 60px;
        background: linear-gradient(to right,
          var(--secondary-background-color) 0%,
          var(--secondary-background-color) 100%);
        border-radius: 8px;
        border: 1px solid var(--divider-color);
        cursor: pointer;
      }
      .timeline-bar {
        position: absolute;
        top: 50%;
        left: 0;
        right: 0;
        height: 4px;
        background-color: var(--divider-color);
        transform: translateY(-50%);
      }
      .timeline-segment {
        position: absolute;
        top: 50%;
        height: 4px;
        transform: translateY(-50%);
        background-color: var(--primary-color);
      }
      .schedule-point {
        position: absolute;
        top: 50%;
        transform: translate(-50%, -50%);
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background-color: var(--primary-color);
        border: 2px solid var(--card-background-color);
        cursor: pointer;
        transition: transform 0.2s;
        z-index: 2;
      }
      .schedule-point:hover {
        transform: translate(-50%, -50%) scale(1.2);
      }
      .schedule-point-label {
        position: absolute;
        top: -24px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 0.7em;
        white-space: nowrap;
        background-color: var(--card-background-color);
        padding: 2px 4px;
        border-radius: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
      }
      .points-list {
        max-height: 200px;
        overflow-y: auto;
      }
      .point-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 12px;
        background-color: var(--secondary-background-color);
        border-radius: 8px;
        margin-bottom: 8px;
      }
      .point-info {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .point-time {
        font-weight: 500;
        font-size: 1.1em;
      }
      .point-temp {
        color: var(--primary-color);
        font-weight: 500;
      }
      .point-delete {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: none;
        background-color: rgba(244, 67, 54, 0.1);
        cursor: pointer;
      }
      .point-delete:hover {
        background-color: rgba(244, 67, 54, 0.2);
      }
      .point-delete ha-icon {
        --mdc-icon-size: 16px;
        color: var(--error-color, #f44336);
      }
      .add-point-section {
        padding: 12px;
        background-color: var(--secondary-background-color);
        border-radius: 8px;
        margin-top: 12px;
      }
      .add-point-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
      }
      .add-point-title {
        font-weight: 500;
      }
      .add-point-form {
        display: flex;
        gap: 8px;
        align-items: flex-end;
      }
      .form-group {
        flex: 1;
      }
      .form-group label {
        display: block;
        font-size: 0.8em;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      .form-group input {
        width: 100%;
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 6px;
        background-color: var(--card-background-color);
        color: var(--primary-text-color);
        font-size: 1em;
      }
      .add-point-btn {
        padding: 8px 16px;
        border: none;
        border-radius: 6px;
        background-color: var(--primary-color);
        color: var(--text-primary-color);
        cursor: pointer;
        font-weight: 500;
      }
      .add-point-btn:hover {
        opacity: 0.9;
      }
      .no-points {
        text-align: center;
        padding: 20px;
        color: var(--secondary-text-color);
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

        ${this._renderStatusIndicators(zoneState, zoneAttrs)}

        <div class="divider"></div>

        <div class="rooms-container">
          ${this._renderRooms(zoneAttrs)}
        </div>

        ${this._showDebug ? this._renderDebug(zoneAttrs) : ""}

        ${this._scheduleModalOpen ? this._renderScheduleModal() : ""}
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

  _renderStatusIndicators(state, attrs) {
    const indicators = [];
    const detailedRooms = attrs.detailed_rooms || [];

    // Count rooms in different states
    const windowOpenRooms = detailedRooms.filter((r) => r.window_confirmed || r.window_open);
    const overheatedRooms = detailedRooms.filter((r) => r.overheated);
    const offRooms = detailedRooms.filter((r) => !r.is_on);

    // Cycle time blocking
    if (attrs.cycle_time_blocking) {
      const timeRemaining = attrs.time_until_cycle_allowed_minutes;
      indicators.push(html`
        <span class="status-chip blocking">
          <ha-icon icon="mdi:timer-sand"></ha-icon>
          Cycle cooldown ${timeRemaining ? `(${timeRemaining.toFixed(1)} min)` : ""}
        </span>
      `);
    }

    // Startup grace period
    if (attrs.startup_grace_period) {
      indicators.push(html`
        <span class="status-chip success">
          <ha-icon icon="mdi:rocket-launch"></ha-icon>
          Startup grace active
        </span>
      `);
    }

    // Away mode pending
    if (attrs.away_mode_pending) {
      indicators.push(html`
        <span class="status-chip info">
          <ha-icon icon="mdi:home-clock"></ha-icon>
          Away in ${attrs.away_mode_delay || "?"} min
        </span>
      `);
    }

    // Windows open
    if (windowOpenRooms.length > 0) {
      const names = windowOpenRooms.map((r) => r.name).join(", ");
      indicators.push(html`
        <span class="status-chip info" title="${names}">
          <ha-icon icon="mdi:window-open-variant"></ha-icon>
          ${windowOpenRooms.length} window${windowOpenRooms.length > 1 ? "s" : ""} open
        </span>
      `);
    }

    // Overheated rooms
    if (overheatedRooms.length > 0) {
      const names = overheatedRooms.map((r) => r.name).join(", ");
      indicators.push(html`
        <span class="status-chip error" title="${names}">
          <ha-icon icon="mdi:thermometer-alert"></ha-icon>
          ${overheatedRooms.length} room${overheatedRooms.length > 1 ? "s" : ""} overheated
        </span>
      `);
    }

    // Rooms off
    if (offRooms.length > 0) {
      const names = offRooms.map((r) => r.name).join(", ");
      indicators.push(html`
        <span class="status-chip neutral" title="${names}">
          <ha-icon icon="mdi:power-off"></ha-icon>
          ${offRooms.length} room${offRooms.length > 1 ? "s" : ""} off
        </span>
      `);
    }

    // If idle and no blocking issues, show satisfied message
    if (state === "idle" && indicators.length === 0) {
      indicators.push(html`
        <span class="status-chip success">
          <ha-icon icon="mdi:check-circle"></ha-icon>
          All rooms at target temperature
        </span>
      `);
    }

    // If no indicators at all
    if (indicators.length === 0) {
      return html``;
    }

    return html`
      <div class="status-indicators">
        ${indicators}
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

    const hasSchedule = room.schedule_enabled;

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
        <div class="room-actions">
          <button
            class="schedule-btn ${hasSchedule ? 'active' : ''}"
            @click=${(e) => this._openScheduleModal(e, room.name)}
            title="Schedule"
          >
            <ha-icon icon="mdi:calendar-clock"></ha-icon>
          </button>
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

  async _openScheduleModal(e, roomName) {
    e.stopPropagation();
    this._selectedRoom = roomName;
    this._activeTab = "weekday";

    try {
      const response = await this.hass.callService(
        "zonal_heating",
        "get_room_schedule",
        { room_name: roomName },
        undefined,
        true,
        true
      );

      if (response && response.response) {
        this._editingSchedule = {
          enabled: response.response.enabled || false,
          weekday: response.response.weekday || [],
          weekend: response.response.weekend || [],
        };
      } else {
        this._editingSchedule = {
          enabled: false,
          weekday: [],
          weekend: [],
        };
      }
    } catch (error) {
      console.error("Failed to load schedule:", error);
      this._editingSchedule = {
        enabled: false,
        weekday: [],
        weekend: [],
      };
    }

    this._scheduleModalOpen = true;
    this.requestUpdate();
  }

  _closeScheduleModal() {
    this._scheduleModalOpen = false;
    this._selectedRoom = null;
    this._editingSchedule = null;
    this.requestUpdate();
  }

  _renderScheduleModal() {
    if (!this._editingSchedule) return html``;

    const points = this._activeTab === "weekday"
      ? this._editingSchedule.weekday
      : this._editingSchedule.weekend;

    return html`
      <div class="modal-overlay" @click=${this._closeScheduleModal}>
        <div class="modal-content" @click=${(e) => e.stopPropagation()}>
          <div class="modal-header">
            <span class="modal-title">${this._selectedRoom} Schedule</span>
            <button class="modal-close" @click=${this._closeScheduleModal}>
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          </div>
          <div class="modal-body">
            <div class="schedule-toggle">
              <span class="schedule-toggle-label">Schedule Enabled</span>
              <input
                type="checkbox"
                .checked=${this._editingSchedule.enabled}
                @change=${this._toggleScheduleEnabled}
              />
            </div>

            <div class="tab-container">
              <button
                class="tab-btn ${this._activeTab === 'weekday' ? 'active' : ''}"
                @click=${() => this._switchTab('weekday')}
              >
                Weekdays (Mon-Fri)
              </button>
              <button
                class="tab-btn ${this._activeTab === 'weekend' ? 'active' : ''}"
                @click=${() => this._switchTab('weekend')}
              >
                Weekends (Sat-Sun)
              </button>
            </div>

            ${this._renderTimeline(points)}

            <div class="points-list">
              ${points.length === 0
                ? html`<div class="no-points">No schedule points. Add one below.</div>`
                : points.map((point) => this._renderPointItem(point))}
            </div>

            ${this._renderAddPointForm()}
          </div>
        </div>
      </div>
    `;
  }

  _renderTimeline(points) {
    const sortedPoints = [...points].sort((a, b) => a.time.localeCompare(b.time));

    return html`
      <div class="timeline-container">
        <div class="timeline-header">
          <span>00:00</span>
          <span>06:00</span>
          <span>12:00</span>
          <span>18:00</span>
          <span>24:00</span>
        </div>
        <div class="timeline">
          <div class="timeline-bar"></div>
          ${sortedPoints.map((point, index) => {
            const pos = this._timeToPercent(point.time);
            return html`
              <div
                class="schedule-point"
                style="left: ${pos}%"
                title="${point.time} - ${point.temperature}°C"
              >
                <span class="schedule-point-label">${point.temperature}°</span>
              </div>
            `;
          })}
        </div>
      </div>
    `;
  }

  _renderPointItem(point) {
    return html`
      <div class="point-item">
        <div class="point-info">
          <span class="point-time">${point.time}</span>
          <span class="point-temp">${point.temperature}°C</span>
        </div>
        <button
          class="point-delete"
          @click=${() => this._removePoint(point.time)}
        >
          <ha-icon icon="mdi:delete"></ha-icon>
        </button>
      </div>
    `;
  }

  _renderAddPointForm() {
    return html`
      <div class="add-point-section">
        <div class="add-point-header">
          <span class="add-point-title">Add Schedule Point</span>
        </div>
        <div class="add-point-form">
          <div class="form-group">
            <label>Time</label>
            <input
              type="time"
              .value=${this._newPointTime}
              @input=${(e) => { this._newPointTime = e.target.value; }}
            />
          </div>
          <div class="form-group">
            <label>Temperature</label>
            <input
              type="number"
              min="5"
              max="30"
              step="0.5"
              .value=${this._newPointTemp}
              @input=${(e) => { this._newPointTemp = parseFloat(e.target.value); }}
            />
          </div>
          <button class="add-point-btn" @click=${this._addPoint}>Add</button>
        </div>
      </div>
    `;
  }

  _timeToPercent(time) {
    const [hours, minutes] = time.split(":").map(Number);
    const totalMinutes = hours * 60 + minutes;
    return (totalMinutes / 1440) * 100;
  }

  _switchTab(tab) {
    this._activeTab = tab;
    this.requestUpdate();
  }

  async _toggleScheduleEnabled(e) {
    this._editingSchedule.enabled = e.target.checked;
    await this._saveSchedule();
  }

  async _addPoint() {
    if (!this._newPointTime || !this._newPointTemp) return;

    try {
      await this.hass.callService("zonal_heating", "add_schedule_point", {
        room_name: this._selectedRoom,
        timeline: this._activeTab,
        time: this._newPointTime,
        temperature: this._newPointTemp,
      });

      const points = this._activeTab === "weekday"
        ? this._editingSchedule.weekday
        : this._editingSchedule.weekend;

      const existingIndex = points.findIndex(p => p.time === this._newPointTime);
      if (existingIndex >= 0) {
        points[existingIndex].temperature = this._newPointTemp;
      } else {
        points.push({ time: this._newPointTime, temperature: this._newPointTemp });
      }
      points.sort((a, b) => a.time.localeCompare(b.time));

      this.requestUpdate();
    } catch (error) {
      console.error("Failed to add schedule point:", error);
    }
  }

  async _removePoint(time) {
    try {
      await this.hass.callService("zonal_heating", "remove_schedule_point", {
        room_name: this._selectedRoom,
        timeline: this._activeTab,
        time: time,
      });

      const points = this._activeTab === "weekday"
        ? this._editingSchedule.weekday
        : this._editingSchedule.weekend;

      const index = points.findIndex(p => p.time === time);
      if (index >= 0) {
        points.splice(index, 1);
      }

      this.requestUpdate();
    } catch (error) {
      console.error("Failed to remove schedule point:", error);
    }
  }

  async _saveSchedule() {
    try {
      await this.hass.callService("zonal_heating", "set_room_schedule", {
        room_name: this._selectedRoom,
        enabled: this._editingSchedule.enabled,
        weekday: this._editingSchedule.weekday,
        weekend: this._editingSchedule.weekend,
      });
    } catch (error) {
      console.error("Failed to save schedule:", error);
    }
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
  "%c ZONAL-HEATING-CARD %c v1.6.1 ",
  "color: white; background: #ff9800; font-weight: bold;",
  "color: #ff9800; background: white; font-weight: bold;"
);
