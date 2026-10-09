import type { Schemas } from "./client";

export type ErrorBody = Schemas["ErrorBody"];

/** A failed API call; `code` is the stable error code of the contract (api.md). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? {};
  }
}

function isErrorBody(value: unknown): value is ErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ErrorBody).code === "string" &&
    typeof (value as ErrorBody).message === "string"
  );
}

export function toApiError(error: unknown, response: Response): ApiError {
  if (isErrorBody(error)) return new ApiError(response.status, error);
  return new ApiError(response.status, {
    code: `http_${response.status}`,
    message: typeof error === "string" && error ? error : response.statusText || "Request failed",
    details: {},
  });
}

/** Return the data of an openapi-fetch result or throw an `ApiError`. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw toApiError(error, response);
  return data as T;
}

export function isApiError(err: unknown, code?: string): err is ApiError {
  return err instanceof ApiError && (code === undefined || err.code === code);
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
