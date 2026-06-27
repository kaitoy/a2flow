/** Redux slice holding transient, auto-dismissing toast notifications. */
import { createSlice, nanoid, type PayloadAction } from "@reduxjs/toolkit";

/** Visual treatment of a toast. */
export type ToastVariant = "success" | "error";

/** A single transient toast message shown by the global `<Toaster />`. */
export interface Toast {
  /** Stable unique id used as the React key and dismissal handle. */
  id: string;
  /** Text shown in the toast. */
  message: string;
  /** Controls icon and color treatment. Defaults to `"success"`. */
  variant: ToastVariant;
}

/** Redux state shape for the toast queue. */
interface ToastState {
  /** Currently visible toasts, oldest first. */
  items: Toast[];
}

const initialState: ToastState = {
  items: [],
};

const toastSlice = createSlice({
  name: "toast",
  initialState,
  reducers: {
    /**
     * Enqueue a new toast. The id is generated automatically; callers pass only
     * the message and (optionally) a variant that defaults to `"success"`.
     */
    showToast: {
      reducer(state, action: PayloadAction<Toast>) {
        state.items.push(action.payload);
      },
      prepare(payload: { message: string; variant?: ToastVariant }) {
        return {
          payload: {
            id: nanoid(),
            message: payload.message,
            variant: payload.variant ?? "success",
          } satisfies Toast,
        };
      },
    },
    /** Remove a toast by id (used by the auto-dismiss timer). */
    dismissToast(state, action: PayloadAction<string>) {
      state.items = state.items.filter((t) => t.id !== action.payload);
    },
  },
});

export const { showToast, dismissToast } = toastSlice.actions;

export default toastSlice.reducer;
