"use client";

import { Provider } from "react-redux";
import { store } from "./index";

/** Wraps the component tree with the Redux store Provider. */
export function StoreProvider({ children }: { children: React.ReactNode }) {
  return <Provider store={store}>{children}</Provider>;
}
