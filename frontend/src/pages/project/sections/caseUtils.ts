export const stepsToText = (steps: string[] | unknown[]) => (steps || []).map((s) => String(s)).join("\n");

export const textToSteps = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
