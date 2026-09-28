const labels = {
  listingTitle: "Listing title",
  propertyAddress: "Property address",
  submitterEmail: "Landlord Email",
  description: "Description",
  propertyType: "Property type",
  termsAccepted: "Terms",
};

export class ApiError extends Error {
  constructor(status, detail) {
    const message = Array.isArray(detail)
      ? detail
          .map(
            (item) =>
              `${labels[item.loc?.at(-1)] || item.loc?.at(-1) || "Input"}: ${item.msg}`,
          )
          .join("; ")
      : typeof detail === "string"
        ? detail
        : "The request could not be completed. Please try again.";
    super(message);
    this.status = status;
  }
}

// A generation counter identifies UI sessions, never a credential or token.
let authEpoch = 0;
export function advanceAuthEpoch() {
  authEpoch += 1;
}

export async function request(
  path,
  { body, notifyUnauthorized = true, ...options } = {},
) {
  const requestEpoch = authEpoch;
  let response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: "include",
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Cannot reach the server. Check your connection and try again.",
    );
  }
  if (response.status === 204) return undefined;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (
      response.status === 401 &&
      notifyUnauthorized &&
      requestEpoch === authEpoch
    )
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(response.status, data?.detail);
  }
  if (data === null)
    throw new Error(
      "The server returned an unreadable response. Please reload.",
    );
  return data;
}

async function mutate(path, options) {
  const result = await request(path, options);
  // A completed write also refreshes a Home that mounted while it was pending.
  window.dispatchEvent(new Event("rentals-changed"));
  return result;
}

export const rentals = {
  list: (query = "", signal) =>
    request(`/rentals${query ? `?q=${encodeURIComponent(query)}` : ""}`, {
      signal,
    }),
  get: (id, signal) => request(`/rentals/${id}`, { signal }),
  create: (body) => mutate("/rentals", { method: "POST", body }),
  update: (id, body) => mutate(`/rentals/${id}`, { method: "PUT", body }),
  remove: (id) => mutate(`/rentals/${id}`, { method: "DELETE" }),
};
