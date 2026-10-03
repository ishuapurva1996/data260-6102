import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { getAuthEpoch, rentals } from "../../api/client.js";

const initialState = () => ({
  epoch: getAuthEpoch(), revision: 0, records: [], total: 0,
  listStatus: "idle", listError: "", listRequestId: null,
  selected: null, detailId: null, detailVisitId: null,
  detailStatus: "idle", detailError: "", detailRequestId: null,
  mutations: {}, lastMutation: null,
});

async function runRequest(operation, { getState, signal, rejectWithValue }) {
  const { epoch, revision } = getState().rentals;
  try { return { result: await operation(signal), epoch, revision }; }
  catch (error) { return rejectWithValue(error.message); }
}

export const fetchRentals = createAsyncThunk("rentals/fetch", (params, api) =>
  runRequest((signal) => rentals.list(params, signal), api));
export const fetchRental = createAsyncThunk("rentals/detail", ({ id }, api) =>
  runRequest((signal) => rentals.get(id, signal), api));

// Conditions run synchronously, so even two dispatches before a render send one write.
function mutation(name, keyFor, operation) {
  return createAsyncThunk(`rentals/${name}`, (arg, api) => runRequest((signal) => operation(arg, signal), api), {
    condition: (arg, { getState }) => getState().rentals.mutations[keyFor(arg)]?.status !== "pending",
  });
}
export const createRental = mutation("create", () => "create", rentals.create);
export const updateRental = mutation("update", ({ id }) => `record:${id}`,
  ({ id, fields }, signal) => rentals.update(id, fields, signal));
export const deleteRental = mutation("delete", (id) => `record:${id}`, rentals.remove);

const slice = createSlice({
  name: "rentals", initialState: initialState(),
  reducers: { clearRentals: () => initialState() },
  extraReducers: (builder) => {
    builder
      .addCase(fetchRentals.pending, (state, action) => {
        state.listStatus = "pending"; state.listError = "";
        state.listRequestId = action.meta.requestId;
      })
      .addCase(fetchRentals.fulfilled, (state, action) => {
        if (state.listRequestId !== action.meta.requestId || state.epoch !== action.payload.epoch || state.revision !== action.payload.revision) return;
        state.records = action.payload.result.records; state.total = action.payload.result.total;
        state.listStatus = "succeeded"; state.listRequestId = null;
      })
      .addCase(fetchRentals.rejected, (state, action) => {
        if (state.listRequestId !== action.meta.requestId) return;
        state.listStatus = action.meta.aborted ? "idle" : "failed";
        state.listError = action.meta.aborted ? "" : action.payload || action.error.message;
        state.listRequestId = null;
      })
      .addCase(fetchRental.pending, (state, action) => {
        const { id, visitId } = action.meta.arg;
        // A new visit initializes from its own completed GET. Same-visit refreshes
        // keep local edits and the submitting form mounted until navigation ends.
        if (state.detailId !== id || state.detailVisitId !== visitId) state.selected = null;
        state.detailId = id; state.detailVisitId = visitId;
        state.detailStatus = "pending"; state.detailError = "";
        state.detailRequestId = action.meta.requestId;
      })
      .addCase(fetchRental.fulfilled, (state, action) => {
        if (state.detailRequestId !== action.meta.requestId || state.epoch !== action.payload.epoch || state.revision !== action.payload.revision) return;
        state.selected = action.payload.result; state.detailStatus = "succeeded";
        state.detailRequestId = null;
      })
      .addCase(fetchRental.rejected, (state, action) => {
        if (state.detailRequestId !== action.meta.requestId) return;
        if (!action.meta.aborted) state.selected = null;
        state.detailStatus = action.meta.aborted ? "idle" : "failed";
        state.detailError = action.meta.aborted ? "" : action.payload || action.error.message;
        state.detailRequestId = null;
      });

    for (const [thunk, keyFor] of [
      [createRental, () => "create"],
      [updateRental, ({ id }) => `record:${id}`],
      [deleteRental, (id) => `record:${id}`],
    ]) {
      builder
        .addCase(thunk.pending, (state, action) => {
          state.mutations[keyFor(action.meta.arg)] = { status: "pending", requestId: action.meta.requestId, error: "" };
        })
        .addCase(thunk.fulfilled, (state, action) => {
          const entry = state.mutations[keyFor(action.meta.arg)];
          if (!entry || entry.requestId !== action.meta.requestId || state.epoch !== action.payload.epoch) return;
          entry.status = "succeeded";
          const record = action.payload.result;
          state.lastMutation = {
            kind: thunk === createRental ? "Added" : thunk === updateRental ? "Updated" : "Deleted",
            id: thunk === deleteRental ? action.meta.arg : record.id,
            record: record || null,
          };
          if (thunk === deleteRental) {
            state.records = state.records.filter((row) => row.id !== action.meta.arg);
            if (state.selected?.id === action.meta.arg) state.selected = null;
          } else {
            state.records = state.records.map((row) => row.id === record.id ? record : row);
            if (state.selected?.id === record.id) state.selected = record;
          }
          // Reads begun before this commit are obsolete. Home reacts to revision
          // and fetches its page; a failed refresh never rejects the completed write.
          state.revision += 1; state.listRequestId = null; state.detailRequestId = null;
          state.listStatus = "idle"; state.listError = "";
        })
        .addCase(thunk.rejected, (state, action) => {
          const entry = state.mutations[keyFor(action.meta.arg)];
          if (!entry || entry.requestId !== action.meta.requestId) return;
          entry.status = "failed"; entry.error = action.payload || action.error.message;
        });
    }
  },
});
export const { clearRentals } = slice.actions;
export default slice.reducer;
