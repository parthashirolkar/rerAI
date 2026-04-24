export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type HitlActionRequest = {
  action?: string;
  name?: string;
  args?: Record<string, unknown>;
  description?: string;
};

type HitlReviewConfig = {
  allowedDecisions?: ("approve" | "reject" | "edit")[];
};

type HitlRequest = {
  actionRequests?: HitlActionRequest[];
  reviewConfigs?: HitlReviewConfig[];
};

export function isHitlRequest(value: unknown): value is HitlRequest {
  return (
    isRecord(value) &&
    Array.isArray(value.actionRequests) &&
    Array.isArray(value.reviewConfigs)
  );
}
