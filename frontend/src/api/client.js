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

export async function request(
  path,
  { body, notifyUnauthorized = true, ...options } = {},
) {
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
    if (response.status === 401 && notifyUnauthorized)
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(response.status, data?.detail);
  }
  if (data === null)
    throw new Error(
      "The server returned an unreadable response. Please reload.",
    );
  return data;
}

export const rentals = {
  list: (query = "", signal) =>
    request(`/rentals${query ? `?q=${encodeURIComponent(query)}` : ""}`, {
      signal,
    }),
  get: (id, signal) => request(`/rentals/${id}`, { signal }),
  create: (body) => request("/rentals", { method: "POST", body }),
  update: (id, body) => request(`/rentals/${id}`, { method: "PUT", body }),
  remove: (id) => request(`/rentals/${id}`, { method: "DELETE" }),
};
