await customElements.whenDefined("ha-panel-lovelace");

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace")
);
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

const SEND_DELAY_MS = 1200;

class ZonalHeatingCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _pending: { type: Object },
      _showDetails: { type: Boolean },
    };
  }

  constructor() {
    super();
    this._pending = {};
    this._timers = {};
    this._showDetails = false;
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
    this._showDetails = config.show_debug || false;
  }

  getCardSize() {
    const zone = this.hass?.states[this.config.zone_sensor];
    return 2 + (zone?.attributes.detailed_rooms?.length || 0);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    Object.values(this._timers).forEach(clearTimeout);
    this._timers = {};
  }

  static get styles() {
    return css`
      :host {
        display: block;
        container-type: inline-size;
        --zh-heat: var(--state-climate-heat-color, #ff8100);
        --zh-ok: var(--success-color, #43a047);
        --zh-window: var(--info-color, #039be5);
        --zh-warn: var(--warning-color, #ffa600);
        --zh-error: var(--error-color, #db4437);
        --zh-off: var(--disabled-text-color, #9e9e9e);
        --zh-radius: var(--bubble-border-radius, 32px);
        --zh-bg: var(
          --bubble-main-background-color,
          var(--ha-card-background, var(--card-background-color))
        );
        --zh-sub-bg: var(
          --bubble-secondary-background-color,
          var(--secondary-background-color)
        );
        --zh-icon-bg: var(
          --bubble-icon-background-color,
          var(--secondary-background-color)
        );
      }
      ha-card {
        background: none;
        border: none;
        box-shadow: none;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .bubble {
        position: relative;
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px;
        border-radius: var(--zh-radius);
        background: var(--zh-bg);
        overflow: hidden;
        isolation: isolate;
      }
      .bubble.lit::before {
        content: "";
        position: absolute;
        inset: 0;
        z-index: -1;
        background: color-mix(in srgb, var(--zh-colour) 18%, transparent);
      }
      .icon {
        flex: none;
        width: 44px;
        height: 44px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        color: var(--zh-colour);
        background: color-mix(in srgb, var(--zh-colour) 22%, var(--zh-icon-bg));
        --mdc-icon-size: 24px;
      }
      .text {
        flex: 1;
        min-width: 0;
        padding-left: 2px;
        cursor: pointer;
        -webkit-tap-highlight-color: transparent;
      }
      .name {
        font-size: 15px;
        font-weight: 600;
        line-height: 1.25;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .state {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        column-gap: 6px;
        font-size: 13px;
        line-height: 1.3;
        color: var(--secondary-text-color);
      }
      .state .temp {
        font-size: 15px;
        font-weight: 600;
        color: var(--primary-text-color);
        font-variant-numeric: tabular-nums;
      }
      .state .label {
        font-weight: 500;
        color: var(--zh-colour);
      }

      .zone {
        padding: 8px;
        min-height: 72px;
        box-sizing: border-box;
      }
      .zone .icon {
        width: 56px;
        height: 56px;
        --mdc-icon-size: 30px;
      }
      .zone .name {
        font-size: 18px;
      }
      .zone .state .label {
        font-size: 15px;
      }
      .why {
        color: var(--secondary-text-color);
      }
      .pill {
        flex: none;
        display: flex;
        align-items: center;
        gap: 6px;
        height: 40px;
        padding: 0 14px;
        margin-right: 4px;
        border-radius: var(--zh-radius);
        background: var(--zh-sub-bg);
        font-size: 14px;
        font-weight: 500;
        --mdc-icon-size: 18px;
      }
      .pill ha-icon {
        color: var(--secondary-text-color);
      }

      .room.off .icon,
      .room.off .text {
        opacity: 0.5;
      }

      .stepper {
        flex: none;
        display: flex;
        align-items: center;
        gap: 2px;
        padding: 3px;
        border-radius: var(--zh-radius);
        background: var(--zh-sub-bg);
      }
      .stepper button {
        width: 40px;
        height: 40px;
        border: none;
        border-radius: 50%;
        background: none;
        color: var(--primary-text-color);
        display: grid;
        place-items: center;
        cursor: pointer;
        --mdc-icon-size: 22px;
        -webkit-tap-highlight-color: transparent;
        touch-action: manipulation;
      }
      .stepper button:active {
        background: color-mix(in srgb, var(--primary-text-color) 12%, transparent);
      }
      .stepper button:disabled {
        opacity: 0.3;
        cursor: default;
      }
      .target {
        min-width: 48px;
        text-align: center;
        font-size: 16px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
      }
      .target.pending {
        color: var(--primary-color);
      }

      .details-toggle {
        align-self: flex-start;
        height: 36px;
        padding: 0 16px;
        border: none;
        border-radius: var(--zh-radius);
        background: var(--zh-bg);
        color: var(--secondary-text-color);
        font: inherit;
        font-size: 13px;
        cursor: pointer;
      }
      .details {
        padding: 12px 18px;
        border-radius: 20px;
        background: var(--zh-bg);
        font-size: 13px;
        color: var(--secondary-text-color);
      }
      .details div {
        padding: 2px 0;
      }
      .details b {
        color: var(--primary-text-color);
        font-weight: 500;
      }

      .missing {
        padding: 16px 20px;
        border-radius: var(--zh-radius);
        background: var(--zh-bg);
        color: var(--zh-error);
      }

      @container (max-width: 400px) {
        .room .icon {
          display: none;
        }
        .text {
          padding-left: 12px;
        }
        .zone .pill {
          display: none;
        }
      }
    `;
  }

  render() {
    if (!this.hass || !this.config) return html``;

    const zone = this.hass.states[this.config.zone_sensor];
    if (!zone) {
      return html`<ha-card>
        <div class="missing">Zone sensor not found: ${this.config.zone_sensor}</div>
      </ha-card>`;
    }

    const attrs = zone.attributes;
    const rooms = attrs.detailed_rooms || [];

    return html`
      <ha-card>
        ${this._renderZone(zone, attrs, rooms)}
        ${rooms.map((room) => this._renderRoom(room, attrs))}
        <button class="details-toggle" @click=${this._toggleDetails}>
          ${this._showDetails ? "Hide details" : "Details"}
        </button>
        ${this._showDetails ? this._renderDetails(attrs) : ""}
      </ha-card>
    `;
  }

  _zoneName(zone, attrs) {
    if (this.config.title && this.config.title.trim()) return this.config.title;
    const name = zone.attributes.friendly_name || attrs.zone_climate || "Heating";
    return name.replace(/^Zonal Heating\s+/i, "").replace(/\s+Status$/i, "");
  }

  _renderZone(zone, attrs, rooms) {
    const calling = rooms.filter((r) => r.calls_for_heat && r.is_on);
    const names = calling.map((r) => r.name).join(", ");
    const wait = attrs.time_until_cycle_allowed_minutes;
    const waitText = wait != null ? `${Math.max(1, Math.ceil(wait))} min` : "";
    let colour = "--zh-ok";
    let icon = "mdi:radiator-off";
    let label = "Off";
    let why = "All rooms are warm";

    if (zone.state === "unavailable" || zone.state === "unknown") {
      colour = "--zh-error";
      icon = "mdi:alert-circle";
      label = "Unavailable";
      why = "The zone thermostat is not responding";
    } else if (attrs.zone_is_on && calling.length) {
      colour = "--zh-heat";
      icon = "mdi:fire";
      label = "Heating";
      why = names;
    } else if (attrs.zone_is_on) {
      colour = "--zh-heat";
      icon = "mdi:fire";
      label = "Heating";
      why = attrs.cycle_time_blocking
        ? `All rooms warm, stopping in ${waitText}`
        : "All rooms warm, stopping";
    } else if (calling.length) {
      colour = "--zh-warn";
      icon = "mdi:timer-sand";
      label = attrs.cycle_time_blocking ? `Starting in ${waitText}` : "Starting";
      why = names;
    } else {
      const off = rooms.filter((r) => !r.is_on).length;
      const windows = rooms.filter((r) => r.is_on && r.window_confirmed).length;
      const parts = [];
      if (windows) parts.push(`${windows} window${windows > 1 ? "s" : ""} open`);
      if (off) parts.push(`${off} room${off > 1 ? "s" : ""} off`);
      if (parts.length) why = `Rooms warm · ${parts.join(" · ")}`;
    }

    const lit = colour === "--zh-heat" || colour === "--zh-warn" || colour === "--zh-error";
    return html`
      <div class="bubble zone ${lit ? "lit" : ""}" style="--zh-colour: var(${colour})">
        <div class="icon"><ha-icon icon=${icon}></ha-icon></div>
        <div class="text" @click=${() => this._moreInfo(attrs.zone_climate)}>
          <div class="name">${this._zoneName(zone, attrs)}</div>
          <div class="state">
            <span class="label">${label}</span>
            ${why ? html`<span class="why">${why}</span>` : ""}
          </div>
        </div>
        ${attrs.zone_current_temp != null
          ? html`<div class="pill">
              <ha-icon icon="mdi:thermostat"></ha-icon>
              ${Number(attrs.zone_current_temp).toFixed(1)}°
            </div>`
          : ""}
      </div>
    `;
  }

  _roomStatus(room, attrs) {
    if (!room.is_on) return ["off", "--zh-off", "mdi:power", "Off"];
    if (room.window_confirmed) {
      return ["window", "--zh-window", "mdi:window-open-variant", "Window open"];
    }
    if (room.window_open) {
      return ["window", "--zh-window", "mdi:window-open-variant", "Window open"];
    }
    if (room.calls_for_heat) {
      return attrs.zone_is_on
        ? ["heat", "--zh-heat", "mdi:fire", "Heating"]
        : ["heat", "--zh-warn", "mdi:timer-sand", "Waiting"];
    }
    if (room.needs_heat && room.demand_stalled) {
      return ["stalled", "--zh-error", "mdi:thermometer-alert", "Not warming"];
    }
    if (room.needs_heat && room.trv_satisfied) {
      return ["valve", "--zh-warn", "mdi:pipe-valve", "Valve closed"];
    }
    return ["ok", "--zh-ok", "mdi:check", "Warm"];
  }

  _climateFor(room) {
    const states = this.hass.states;
    const ids = Object.keys(states).filter((id) => id.startsWith("climate."));
    if (room.trv_entity) {
      const match = ids.find(
        (id) => states[id].attributes.trv_entity === room.trv_entity
      );
      if (match) return match;
    }
    const suffix = ` ${room.name}`.toLowerCase();
    return ids.find((id) => {
      const a = states[id].attributes;
      return a.trv_entity && (a.friendly_name || "").toLowerCase().endsWith(suffix);
    });
  }

  _renderRoom(room, attrs) {
    const [cls, colour, icon, label] = this._roomStatus(room, attrs);
    const entityId = this._climateFor(room);
    const climate = entityId ? this.hass.states[entityId] : null;
    const pending = entityId ? this._pending[entityId] : undefined;
    const target = pending ?? climate?.attributes.temperature ?? room.target_temp;
    const min = climate?.attributes.min_temp ?? 5;
    const max = climate?.attributes.max_temp ?? 30;
    const current =
      room.current_temp != null ? `${Number(room.current_temp).toFixed(1)}°` : "--";

    return html`
      <div
        class="bubble room ${cls} ${cls === "heat" ? "lit" : ""}"
        style="--zh-colour: var(${colour})"
      >
        <div class="icon"><ha-icon icon=${icon}></ha-icon></div>
        <div class="text" @click=${() => this._moreInfo(entityId)}>
          <div class="name">${room.name}</div>
          <div class="state">
            <span class="temp">${current}</span>
            <span class="label">${label}</span>
          </div>
        </div>
        <div class="stepper">
          <button
            aria-label="Lower ${room.name} target"
            ?disabled=${!entityId || target == null || target <= min}
            @click=${() => this._step(entityId, target, -this._stepSize(climate), min, max)}
          >
            <ha-icon icon="mdi:minus"></ha-icon>
          </button>
          <div class="target ${pending != null ? "pending" : ""}">
            ${target != null ? `${Number(target).toFixed(1)}°` : "--"}
          </div>
          <button
            aria-label="Raise ${room.name} target"
            ?disabled=${!entityId || target == null || target >= max}
            @click=${() => this._step(entityId, target, this._stepSize(climate), min, max)}
          >
            <ha-icon icon="mdi:plus"></ha-icon>
          </button>
        </div>
      </div>
    `;
  }

  _stepSize(climate) {
    return climate?.attributes.target_temp_step || this.config.step || 0.5;
  }

  _step(entityId, target, delta, min, max) {
    if (!entityId || target == null) return;
    const next = Math.min(max, Math.max(min, Math.round((target + delta) * 10) / 10));
    this._pending = { ...this._pending, [entityId]: next };
    clearTimeout(this._timers[entityId]);
    this._timers[entityId] = setTimeout(() => this._send(entityId), SEND_DELAY_MS);
  }

  async _send(entityId) {
    const temperature = this._pending[entityId];
    delete this._timers[entityId];
    try {
      await this.hass.callService("climate", "set_temperature", {
        entity_id: entityId,
        temperature,
      });
    } finally {
      this._timers[entityId] = setTimeout(() => {
        delete this._timers[entityId];
        if (this._pending[entityId] === temperature) {
          const { [entityId]: _, ...rest } = this._pending;
          this._pending = rest;
        }
      }, SEND_DELAY_MS * 5);
    }
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  _renderDetails(attrs) {
    const rooms = attrs.detailed_rooms || [];
    const yesNo = (v) => (v ? "yes" : "no");
    return html`
      <div class="details">
        <div>${attrs.reason || ""}</div>
        <div>
          Thermostat <b>${attrs.zone_climate}</b> is
          <b>${attrs.zone_is_on ? "on" : "off"}</b>, last changed
          <b>${attrs.time_since_last_change_minutes ?? "?"} min</b> ago
          (min on ${attrs.min_on_time_minutes} / off ${attrs.min_off_time_minutes} min)
        </div>
        ${rooms.map(
          (r) => html`<div>
            <b>${r.name}</b>: needs heat ${yesNo(r.needs_heat)}, calling
            ${yesNo(r.calls_for_heat)}, valve closed ${yesNo(r.trv_satisfied)},
            not warming ${yesNo(r.demand_stalled)}
          </div>`
        )}
      </div>
    `;
  }

  _toggleDetails() {
    this._showDetails = !this._showDetails;
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
