import { describe, expect, it } from "vitest";

import {
  configToPayload,
  configValuesFromMachineConfig,
  emptyConfigValues,
  parseNumber,
  validateConfig,
} from "./validation";
import { configFixture } from "../test/fixtures";

describe("config defaults", () => {
  it("returns the documented defaults", () => {
    expect(emptyConfigValues()).toEqual({
      cube: { x: "-750", y: "750", z: "0" },
      destination: { x: "700", y: "-700", z: "0" },
      home: { x: "0", y: "0", z: "0" },
      speed: "90",
      approachHeight: "100",
    });
  });

  it("converts a server config to strings", () => {
    const values = configValuesFromMachineConfig(configFixture());
    expect(values.cube).toEqual({ x: "-750", y: "750", z: "0" });
    expect(values.destination).toEqual({ x: "700", y: "-700", z: "0" });
    expect(values.home).toEqual({ x: "0", y: "0", z: "0" });
    expect(values.speed).toBe("90");
    expect(values.approachHeight).toBe("100");
  });

  it("falls back to defaults for an undefined config", () => {
    expect(configValuesFromMachineConfig(undefined)).toEqual(emptyConfigValues());
  });
});

describe("parseNumber", () => {
  it("parses finite numbers and rejects blanks", () => {
    expect(parseNumber("42")).toBe(42);
    expect(parseNumber("-1.5")).toBe(-1.5);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("   ")).toBeNull();
    expect(parseNumber("nope")).toBeNull();
    expect(parseNumber("Infinity")).toBeNull();
  });
});

describe("validateConfig", () => {
  it("accepts the defaults", () => {
    expect(validateConfig(emptyConfigValues())).toEqual({});
  });

  it("requires numeric coordinates", () => {
    const values = emptyConfigValues();
    values.cube.x = "";
    expect(validateConfig(values)["cube.x"]).toMatch(/Enter a number/);
  });

  it("enforces the robot limits", () => {
    const values = emptyConfigValues();
    values.cube.x = "1001";
    values.destination.y = "-1001";
    values.home.z = "1001";
    const errors = validateConfig(values);
    expect(errors["cube.x"]).toMatch(/within/);
    expect(errors["destination.y"]).toMatch(/within/);
    expect(errors["home.z"]).toMatch(/within/);
  });

  it("keeps tables at or above Z 0 and allows a negative home", () => {
    const values = emptyConfigValues();
    values.cube.z = "-1";
    values.destination.z = "-2";
    values.home.z = "-1000";
    const errors = validateConfig(values);
    expect(errors["cube.z"]).toMatch(/table surface/);
    expect(errors["destination.z"]).toMatch(/table surface/);
    expect(errors["home.z"]).toBeUndefined();
  });

  it("validates speed", () => {
    const values = emptyConfigValues();
    values.speed = "0";
    expect(validateConfig(values).speed).toMatch(/1–100/);
    values.speed = "101";
    expect(validateConfig(values).speed).toMatch(/1–100/);
    values.speed = "90.5";
    expect(validateConfig(values).speed).toMatch(/whole number/);
    values.speed = "";
    expect(validateConfig(values).speed).toMatch(/whole number/);
  });

  it("validates approach height and the combined Z", () => {
    const values = emptyConfigValues();
    values.approachHeight = "-1";
    expect(validateConfig(values).approachHeight).toMatch(/0–1000/);
    values.approachHeight = "1001";
    expect(validateConfig(values).approachHeight).toMatch(/0–1000/);

    values.approachHeight = "100";
    values.cube.z = "950";
    expect(validateConfig(values)["cube.z"]).toMatch(/Z \+ approach/);
    values.destination.z = "950";
    expect(validateConfig(values)["destination.z"]).toMatch(/Z \+ approach/);
  });

  it("allows the exact boundary", () => {
    const values = emptyConfigValues();
    values.cube.z = "900";
    values.destination.z = "900";
    values.approachHeight = "100";
    expect(validateConfig(values)).toEqual({});
  });
});

describe("configToPayload", () => {
  it("converts a valid form to numbers", () => {
    expect(configToPayload(emptyConfigValues())).toEqual({
      cubePosition: { x: -750, y: 750, z: 0 },
      destinationPosition: { x: 700, y: -700, z: 0 },
      homePosition: { x: 0, y: 0, z: 0 },
      speed: 90,
      approachHeight: 100,
    });
  });

  it("returns null for invalid values", () => {
    const values = emptyConfigValues();
    values.speed = "0";
    expect(configToPayload(values)).toBeNull();
  });
});
