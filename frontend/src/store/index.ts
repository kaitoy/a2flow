/** Redux store configuration combining the chat, auth, notifications, and toast slices. */
import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./authSlice";
import chatReducer from "./chatSlice";
import notificationsReducer from "./notificationsSlice";
import toastReducer from "./toastSlice";

export const store = configureStore({
  reducer: {
    chat: chatReducer,
    auth: authReducer,
    notifications: notificationsReducer,
    toast: toastReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
