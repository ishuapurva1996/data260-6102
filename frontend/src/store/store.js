import { configureStore } from "@reduxjs/toolkit";
import rentals from "../features/rentals/rentalsSlice.js";

export const store = configureStore({ reducer: { rentals } });
