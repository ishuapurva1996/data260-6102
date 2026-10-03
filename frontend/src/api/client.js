import axios from "axios";

const labels = {
  listingTitle: "Listing title", propertyAddress: "Property address",
  submitterEmail: "Landlord Email", description: "Description",
  propertyType: "Property type", termsAccepted: "Terms",
  listingCode: "Listing code", availableUnits: "Available units",
  managerId: "Property manager",
};

export class ApiError extends Error {
  constructor(status, detail) {
    super(Array.isArray(detail)
      ? detail.map((item) => `${labels[item.loc?.at(-1)] || item.loc?.at(-1) || "Input"}: ${item.msg}`).join("; ")
      : typeof detail === "string" ? detail : "The request could not be completed. Please try again.");
    this.status = status;
  }
}

// A UI session generation is never a credential. Old 401s cannot expire a new login.
let authEpoch = 0;
export const getAuthEpoch = () => authEpoch;
export function advanceAuthEpoch() { return ++authEpoch; }
const client = axios.create({ baseURL: "/api", withCredentials: true, timeout: 30000 });

export async function request(path, { body, notifyUnauthorized = true, page = false, ...options } = {}) {
  const epoch = getAuthEpoch();
  try {
    const response = await client.request({ url: path, data: body, ...options });
    if (response.status === 204) return undefined;
    if (response.data === null || typeof response.data !== "object")
      throw new Error("The server returned an unreadable response. Please reload.");
    if (!page) return response.data;
    const total = Number(response.headers["x-total-count"]);
    if (!Array.isArray(response.data) || !Number.isSafeInteger(total) || total < 0)
      throw new Error("The server returned invalid pagination information. Please reload.");
    return { records: response.data, total };
  } catch (error) {
    if (axios.isCancel(error)) throw error;
    if (!axios.isAxiosError(error)) throw error;
    if (!error.response)
      throw new Error("Cannot reach the server. Check your connection and try again.");
    if (error.response.status === 401 && notifyUnauthorized && epoch === getAuthEpoch())
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(error.response.status, error.response.data?.detail);
  }
}

export const rentals = {
  list: ({ query = "", limit = 50, offset = 0 } = {}, signal) =>
    request("/rentals", { params: { q: query, limit, offset }, signal, page: true }),
  get: (id, signal) => request(`/rentals/${id}`, { signal }),
  create: (body, signal) => request("/rentals", { method: "POST", body, signal }),
  update: (id, body, signal) => request(`/rentals/${id}`, { method: "PUT", body, signal }),
  remove: (id, signal) => request(`/rentals/${id}`, { method: "DELETE", signal }),
};

export async function listManagers(signal) {
  const records = [];
  let total;
  do {
    const page = await request("/property-managers", {
      params: { limit: 100, offset: records.length }, signal, page: true,
    });
    records.push(...page.records);
    total = page.total;
    if (!page.records.length) break;
  } while (records.length < total);
  return records;
}
