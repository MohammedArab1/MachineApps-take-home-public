import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import type {
  AxisValues,
  CommandMessage,
  ConfigValues,
  MachineConfig,
} from "../types";
import {
  configValuesFromMachineConfig,
  validateConfig,
  type ConfigErrors,
} from "../lib/validation";

interface ConfigFormProps {
  config: MachineConfig | undefined;
  connected: boolean;
  busy: boolean;
  onSave: (values: ConfigValues) => Promise<CommandMessage>;
}

interface PositionFieldsProps {
  name: string;
  legend: string;
  prefix: "cube" | "destination" | "home";
  values: AxisValues;
  errors: ConfigErrors;
  disabled: boolean;
  onChange: (axis: keyof AxisValues, value: string) => void;
}

const AXES = ["x", "y", "z"] as const;

function PositionFields({
  name,
  legend,
  prefix,
  values,
  errors,
  disabled,
  onChange,
}: PositionFieldsProps) {
  return (
    <fieldset className="position-group" disabled={disabled}>
      <legend>{legend}</legend>
      <div className="position-inputs">
        {AXES.map((axis) => {
          const id = `${prefix}-${axis}`;
          const error = errors[`${prefix}.${axis}`];
          return (
            <label className="axis-field" htmlFor={id} key={axis}>
              <span>{axis.toUpperCase()}</span>
              <input
                id={id}
                aria-label={`${name} ${axis.toUpperCase()}`}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? `${id}-error` : undefined}
                type="number"
                inputMode="decimal"
                step="any"
                value={values[axis]}
                onChange={(event) => onChange(axis, event.target.value)}
              />
              {error && (
                <small className="field-error" id={`${id}-error`}>
                  {error}
                </small>
              )}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function ConfigForm({
  config,
  connected,
  busy,
  onSave,
}: ConfigFormProps) {
  const [values, setValues] = useState<ConfigValues>(() =>
    configValuesFromMachineConfig(config),
  );
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<CommandMessage | null>(null);
  const lastServerKey = useRef<string | null>(null);

  const serverValues = useMemo(
    () => configValuesFromMachineConfig(config),
    [config],
  );
  const serverKey = JSON.stringify(serverValues);

  useEffect(() => {
    if (!dirty && lastServerKey.current !== serverKey) {
      lastServerKey.current = serverKey;
      setValues(serverValues);
    }
  }, [dirty, serverKey, serverValues]);

  const errors = validateConfig(values);
  const hasErrors = Object.keys(errors).length > 0;
  const disabled = !connected || busy || saving;

  const updateAxis = (
    group: "cube" | "destination" | "home",
    axis: keyof AxisValues,
    value: string,
  ) => {
    setValues((previous) => ({
      ...previous,
      [group]: { ...previous[group], [axis]: value },
    }));
    setDirty(true);
    setMessage(null);
  };

  const updateScalar = (
    key: "speed" | "approachHeight",
    value: string,
  ) => {
    setValues((previous) => ({ ...previous, [key]: value }));
    setDirty(true);
    setMessage(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (hasErrors || !dirty || disabled) return;

    setSaving(true);
    setMessage(null);
    try {
      const result = await onSave(values);
      setMessage(result);
      if (result.ok) setDirty(false);
    } catch (error) {
      setMessage({
        ok: false,
        message:
          error instanceof Error && error.message
            ? error.message
            : "The configuration could not be saved.",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReload = () => {
    setValues(serverValues);
    lastServerKey.current = serverKey;
    setDirty(false);
    setMessage(null);
  };

  return (
    <section className="panel config" aria-labelledby="config-heading">
      <div className="panel-heading">
        <div>
          <h2 id="config-heading">Configuration</h2>
          <p className="panel-subtitle">
            Persisted through vention-storage on the backend
          </p>
        </div>
        <span className={`config-state ${dirty ? "config-state--dirty" : ""}`}>
          {dirty ? "Unsaved changes" : "Saved"}
        </span>
      </div>

      <form className="config-form" onSubmit={handleSubmit} noValidate>
        <PositionFields
          name="Cube"
          legend="Cube start — Table A"
          prefix="cube"
          values={values.cube}
          errors={errors}
          disabled={disabled}
          onChange={(axis, value) => updateAxis("cube", axis, value)}
        />
        <PositionFields
          name="Destination"
          legend="Destination — Table B"
          prefix="destination"
          values={values.destination}
          errors={errors}
          disabled={disabled}
          onChange={(axis, value) => updateAxis("destination", axis, value)}
        />
        <PositionFields
          name="Home"
          legend="Home position"
          prefix="home"
          values={values.home}
          errors={errors}
          disabled={disabled}
          onChange={(axis, value) => updateAxis("home", axis, value)}
        />

        <fieldset className="motion-group" disabled={disabled}>
          <legend>Motion</legend>
          <div className="motion-inputs">
            <label className="scalar-field" htmlFor="speed">
              <span>Speed (mm/s)</span>
              <input
                id="speed"
                type="number"
                inputMode="numeric"
                min={1}
                max={100}
                step={1}
                value={values.speed}
                aria-invalid={Boolean(errors.speed)}
                aria-describedby={errors.speed ? "speed-error" : undefined}
                onChange={(event) => updateScalar("speed", event.target.value)}
              />
              {errors.speed && (
                <small className="field-error" id="speed-error">
                  {errors.speed}
                </small>
              )}
            </label>
            <label className="scalar-field" htmlFor="approachHeight">
              <span>Approach height (mm)</span>
              <input
                id="approachHeight"
                type="number"
                inputMode="decimal"
                min={0}
                max={1000}
                step="any"
                value={values.approachHeight}
                aria-invalid={Boolean(errors.approachHeight)}
                aria-describedby={
                  errors.approachHeight ? "approach-height-error" : undefined
                }
                onChange={(event) =>
                  updateScalar("approachHeight", event.target.value)
                }
              />
              {errors.approachHeight && (
                <small className="field-error" id="approach-height-error">
                  {errors.approachHeight}
                </small>
              )}
            </label>
          </div>
        </fieldset>

        {message && (
          <p
            className={`form-message form-message--${message.ok ? "ok" : "error"}`}
            role={message.ok ? "status" : "alert"}
            data-testid="config-message"
          >
            {message.message}
          </p>
        )}

        <div className="form-actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={disabled || !dirty || hasErrors}
            aria-busy={saving}
          >
            {saving ? "Saving…" : "Save configuration"}
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={handleReload}
            disabled={disabled || !dirty}
          >
            Discard changes
          </button>
        </div>
      </form>
    </section>
  );
}

