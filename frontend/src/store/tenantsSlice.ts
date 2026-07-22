/** Redux slice signaling that the tenant list has changed, so admin-wide tenant pickers refetch. */
import { createSlice } from "@reduxjs/toolkit";

/** Redux state shape for the tenant-list refresh signal. */
interface TenantsState {
  /** Incremented whenever a tenant is created, updated, or deleted; pickers refetch when it changes. */
  version: number;
}

const initialState: TenantsState = {
  version: 0,
};

const tenantsSlice = createSlice({
  name: "tenants",
  initialState,
  reducers: {
    /** Signal that the tenant list changed elsewhere in the app. */
    tenantsChanged(state) {
      state.version += 1;
    },
  },
});

export const { tenantsChanged } = tenantsSlice.actions;
export default tenantsSlice.reducer;
