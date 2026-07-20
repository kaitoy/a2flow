/** Redux store configuration combining the chat, auth, notifications, tenants, and toast slices. */
import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./authSlice";
import chatReducer from "./chatSlice";
import notificationsReducer from "./notificationsSlice";
import tenantsReducer from "./tenantsSlice";
import toastReducer from "./toastSlice";

export const store = configureStore({
  reducer: {
    chat: chatReducer,
    auth: authReducer,
    notifications: notificationsReducer,
    tenants: tenantsReducer,
    toast: toastReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
