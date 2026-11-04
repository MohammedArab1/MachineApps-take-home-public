import type { AxisValues, ConfigPayload, ConfigValues, MachineConfig } from "../types";

export const LIMIT = 1000;

export type ConfigErrors = Record<string, string>;

const AXES = ["x", "y", "z"] as const;

function defaultAxis(): AxisValues {
  return { x: "0", y: "0", z: "0" };
}

export function emptyConfigValues(): ConfigValues {
  return {
    cube: { x: "-750", y: "750", z: "0" },
    destination: { x: "700", y: "-700", z: "0" },
    home: defaultAxis(),
    speed: "90",
    approachHeight: "100",
  };
}

function axisFrom(position: { x: number; y: number; z: number } | undefined): AxisValues {
  return {
    x: String(position?.x ?? 0),
    y: String(position?.y ?? 0),
    z: String(position?.z ?? 0),
  };
}

export function configValuesFromMachineConfig(
  config: MachineConfig | undefined,
): ConfigValues {
  if (!config) return emptyConfigValues();
  return {
    cube: axisFrom(config.cubePosition),
    destination: axisFrom(config.destinationPosition),
    home: axisFrom(config.homePosition),
    speed: String(config.speed ?? 90),
    approachHeight: String(config.approachHeight ?? 100),
  };
}

export function parseNumber(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function validateConfig(values: ConfigValues): ConfigErrors {
  const errors: ConfigErrors = {};

  const checkPosition = (
    prefix: "cube" | "destination" | "home",
    axisValues: AxisValues,
    allowNegativeZ: boolean,
  ) => {
    for (const axis of AXES) {
      const value = parseNumber(axisValues[axis]);
      if (value === null) {
        errors[`${prefix}.${axis}`] = "Enter a number.";
        continue;
      }
      if (Math.abs(value) > LIMIT) {
        errors[`${prefix}.${axis}`] = "Must be within ±1000 mm.";
      }
    }
    const z = parseNumber(axisValues.z);
    if (z !== null && !allowNegativeZ && z < 0) {
      errors[`${prefix}.z`] = "The table surface is Z 0.";
    }
  };

  checkPosition("cube", values.cube, false);
  checkPosition("destination", values.destination, false);
  checkPosition("home", values.home, true);

  const speed = parseNumber(values.speed);
  if (speed === null || !Number.isInteger(speed)) {
    errors.speed = "Enter a whole number.";
  } else if (speed < 1 || speed > 100) {
    errors.speed = "Speed must be 1–100 mm/s.";
  }

  const approach = parseNumber(values.approachHeight);
  if (approach === null) {
    errors.approachHeight = "Enter a number.";
  } else if (approach < 0 || approach > LIMIT) {
    errors.approachHeight = "Approach height must be 0–1000 mm.";
  } else {
    const cubeZ = parseNumber(values.cube.z);
    const destinationZ = parseNumber(values.destination.z);
    if (cubeZ !== null && cubeZ + approach > LIMIT) {
      errors["cube.z"] = "Z + approach must be ≤ 1000 mm.";
    }
    if (destinationZ !== null && destinationZ + approach > LIMIT) {
      errors["destination.z"] = "Z + approach must be ≤ 1000 mm.";
    }
  }

  return errors;
}

export function configToPayload(values: ConfigValues): ConfigPayload | null {
  if (Object.keys(validateConfig(values)).length > 0) return null;

  return {
    cubePosition: {
      x: Number(values.cube.x),
      y: Number(values.cube.y),
      z: Number(values.cube.z),
    },
    destinationPosition: {
      x: Number(values.destination.x),
      y: Number(values.destination.y),
      z: Number(values.destination.z),
    },
    homePosition: {
      x: Number(values.home.x),
      y: Number(values.home.y),
      z: Number(values.home.z),
    },
    speed: Number(values.speed),
    approachHeight: Number(values.approachHeight),
  };
}
