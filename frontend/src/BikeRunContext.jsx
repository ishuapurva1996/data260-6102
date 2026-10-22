import React, { createContext, useContext, useState } from "react";

const BikeRunContext = createContext(null);

export function BikeRunSession({ children }) {
  const state = useState(null);
  return <BikeRunContext.Provider value={state}>{children}</BikeRunContext.Provider>;
}

export function useBikeRun() {
  const state = useContext(BikeRunContext);
  if (!state) throw new Error("Bike-share requires an authenticated run session.");
  return state;
}
