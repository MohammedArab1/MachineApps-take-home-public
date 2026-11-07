import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SceneView } from "./SceneView";
import { configFixture, position, statusFixture } from "../test/fixtures";

function numericAttribute(element: HTMLElement, name: string): number {
  return Number(element.getAttribute(name));
}

function translateAttribute(element: HTMLElement): { x: number; y: number } {
  const match = /translate\(([-\d.]+)[ ,]+([-\d.]+)\)/.exec(
    element.getAttribute("transform") ?? "",
  );
  return { x: Number(match?.[1]), y: Number(match?.[2]) };
}

describe("SceneView", () => {
  it("places the robot, cube, destination, and Z marker", () => {
    render(
      <SceneView
        status={statusFixture({
          robotPosition: position(0, 0, 100),
          config: configFixture(),
        })}
      />,
    );

    const robot = screen.getByTestId("scene-robot");
    expect(numericAttribute(robot, "cx")).toBeCloseTo(320);
    expect(numericAttribute(robot, "cy")).toBeCloseTo(320);

    const cube = translateAttribute(screen.getByTestId("scene-cube"));
    expect(cube.x).toBeCloseTo(140.6);
    expect(cube.y).toBeCloseTo(140.6);
    expect(screen.getByTestId("scene-cube-label")).toHaveTextContent("Cube");

    const destination = screen.getByTestId("scene-destination");
    expect(numericAttribute(destination, "cx")).toBeCloseTo(493.88);
    expect(numericAttribute(destination, "cy")).toBeCloseTo(471.8);

    const zMarker = screen.getByTestId("scene-z-marker");
    expect(numericAttribute(zMarker, "cy")).toBeCloseTo(512);

    expect(screen.getByTestId("scene-table-a")).toBeInTheDocument();
    const tableB = screen.getByTestId("scene-table-b");
    expect(tableB.tagName.toLowerCase()).toBe("polygon");
    expect((tableB.getAttribute("points") ?? "").split(" ")).toHaveLength(4);
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("Robot at X 0.0"),
    );
  });

  it("draws the cube as a solid object at its live position", () => {
    render(
      <SceneView
        status={statusFixture({
          robotPosition: position(320, -180, 140),
          cubePosition: position(320, -180, 140),
          cubeLocation: "held",
          config: configFixture(),
        })}
      />,
    );

    const cube = translateAttribute(screen.getByTestId("scene-cube"));
    expect(cube.x).toBeCloseTo(408.32);
    expect(cube.y).toBeCloseTo(369.68);
    expect(screen.getByTestId("scene-cube-label")).toHaveTextContent(
      "Cube (held)",
    );
  });

  it("clamps positions outside the workspace for display", () => {
    render(
      <SceneView
        status={statusFixture({
          robotPosition: position(5000, -5000, 2000),
          config: configFixture(),
        })}
      />,
    );

    const robot = screen.getByTestId("scene-robot");
    expect(numericAttribute(robot, "cx")).toBeCloseTo(596);
    expect(numericAttribute(robot, "cy")).toBeCloseTo(596);
    const zMarker = screen.getByTestId("scene-z-marker");
    expect(numericAttribute(zMarker, "cy")).toBeCloseTo(80);
  });

  it("adds a fault class and label", () => {
    const { container } = render(
      <SceneView
        status={statusFixture({ state: "fault", step: "Fault", fault: "boom" })}
      />,
    );

    expect(container.querySelector(".scene")).toHaveClass("scene--fault");
    expect(screen.getByText("Fault")).toBeInTheDocument();
  });

  it("renders safely without robot or config data", () => {
    render(
      <SceneView
        status={statusFixture({ robotPosition: undefined, config: undefined })}
      />,
    );

    expect(screen.getByTestId("scene-robot")).toBeInTheDocument();
    expect(screen.getByTestId("scene-cube")).toBeInTheDocument();
    expect(screen.getByTestId("scene-destination")).toBeInTheDocument();
  });
});
