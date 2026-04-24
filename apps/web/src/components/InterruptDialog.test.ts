import { describe, expect, test } from "bun:test";

import { isHitlRequest, isRecord } from "./interruptHelpers";

describe("interrupt payload normalization", () => {
  test("isRecord rejects primitives and arrays", () => {
    expect(isRecord(null)).toBe(false);
    expect(isRecord(undefined)).toBe(false);
    expect(isRecord("string")).toBe(false);
    expect(isRecord(123)).toBe(false);
    expect(isRecord([])).toBe(false);
    expect(isRecord({})).toBe(true);
    expect(isRecord({ a: 1 })).toBe(true);
  });

  test("isHitlRequest requires both actionRequests and reviewConfigs arrays", () => {
    expect(isHitlRequest(null)).toBe(false);
    expect(isHitlRequest({})).toBe(false);
    expect(isHitlRequest({ actionRequests: [] })).toBe(false);
    expect(isHitlRequest({ reviewConfigs: [] })).toBe(false);
    expect(isHitlRequest({ actionRequests: [], reviewConfigs: [] })).toBe(true);
    expect(
      isHitlRequest({
        actionRequests: [{ name: "test" }],
        reviewConfigs: [{ allowedDecisions: ["approve"] }],
      })
    ).toBe(true);
  });

  test("isHitlRequest rejects malformed payloads gracefully", () => {
    expect(isHitlRequest({ actionRequests: "bad", reviewConfigs: [] })).toBe(false);
    expect(isHitlRequest({ actionRequests: [], reviewConfigs: "bad" })).toBe(false);
    expect(isHitlRequest({ actionRequests: [1, 2], reviewConfigs: [3, 4] })).toBe(true);
    expect(isHitlRequest([{ actionRequests: [], reviewConfigs: [] }])).toBe(false);
  });
});
