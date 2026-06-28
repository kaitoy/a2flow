/** Redux slice holding the current user's notifications and unread count. */
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { Notification } from "@/lib/api";

/** Lifecycle of the most recent notifications fetch. */
export type NotificationsStatus = "idle" | "loading" | "error";

/** Redux state shape for the notification center. */
interface NotificationsState {
  /** All notifications for the current user, newest first. */
  items: Notification[];
  /** Number of `items` that are still unread (drives the toolbar badge). */
  unreadCount: number;
  /** Status of the latest fetch performed by the polling hook. */
  status: NotificationsStatus;
}

const initialState: NotificationsState = {
  items: [],
  unreadCount: 0,
  status: "idle",
};

/** Count how many notifications in the list are unread. */
function countUnread(items: Notification[]): number {
  return items.reduce((n, item) => (item.read ? n : n + 1), 0);
}

const notificationsSlice = createSlice({
  name: "notifications",
  initialState,
  reducers: {
    /** Mark a fetch as in flight. */
    notificationsLoading(state) {
      state.status = "loading";
    },
    /** Replace the notification list with a freshly fetched page and recompute the unread count. */
    setNotifications(state, action: PayloadAction<Notification[]>) {
      state.items = action.payload;
      state.unreadCount = countUnread(action.payload);
      state.status = "idle";
    },
    /** Mark the latest fetch as failed without discarding the existing list. */
    notificationsError(state) {
      state.status = "error";
    },
    /** Optimistically mark a single notification as read and decrement the unread count. */
    markReadLocal(state, action: PayloadAction<string>) {
      const item = state.items.find((n) => n.id === action.payload);
      if (item && !item.read) {
        item.read = true;
        state.unreadCount = countUnread(state.items);
      }
    },
    /** Optimistically remove a single notification and recompute the unread count. */
    removeLocal(state, action: PayloadAction<string>) {
      state.items = state.items.filter((n) => n.id !== action.payload);
      state.unreadCount = countUnread(state.items);
    },
    /** Optimistically mark every notification as read and zero the unread count. */
    markAllReadLocal(state) {
      for (const item of state.items) item.read = true;
      state.unreadCount = 0;
    },
  },
});

export const {
  notificationsLoading,
  setNotifications,
  notificationsError,
  markReadLocal,
  removeLocal,
  markAllReadLocal,
} = notificationsSlice.actions;

export default notificationsSlice.reducer;
